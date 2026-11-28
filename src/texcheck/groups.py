"""Sort findings into groups, so the likely mistakes come first.

A book's spelling findings are mostly not mistakes: foreign phrases, dialect
in dialogue, names, words aspell knows only in another form. Left in one
list, the few real typos are buried. So each unknown word is put in a group,
judged from all its uses, and the groups are shown likely typos first.

The rules are heuristics, an aid to reading and not a verdict; `classify`
says which wins when several apply. Stages other than spelling keep one
group each, in the order they run.
"""

import re
import unicodedata
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field

from . import dictionaries
from .checks.languagetool import KINDS as LANGUAGETOOL_GROUPS
from .commands import KNOWN_COMMANDS
from .prose import Prose, Source
from .run import Located, Run, context_of

#: Spelling's groups, in the order they are shown.
SPELLING_GROUPS = [
    ("latex", "Wrong LaTeX?", "a command that lost its backslash, read as a word"),
    ("typos", "Likely typos", "words aspell can correct, not names"),
    ("other", "Other unknown words", "aspell has no suggestion"),
    ("quotes", "In quotations", "dialogue, dialect and quoted words"),
    ("bold", "Foreign and bold phrases", "set in bold, often not English"),
    ("names", "Names", "capitalised mid-sentence"),
    ("variants", "Variants", "known in another case, spacing or accent"),
    ("elsewhere", "Probably correct", "aspell lacks them, but a larger dictionary has them"),
]

#: The spelling group shown after every stage, not with the rest of
#: spelling: words another dictionary vouches for are the least likely
#: mistakes, so they come last.
LAST = "elsewhere"

#: The note for a word only macOS knows: its yes may be a word someone
#: "learned" on this Mac, so it is worth a closer look.
MAC_ONLY = "only this Mac knows it"

#: Layout's groups, in the order they are shown, keyed by the finding's kind.
LAYOUT_GROUPS = [
    ("part-left", "Part pages on the left", "a part's own page should be a right-hand one"),
    ("title-foot", "Headings at the foot of a page", "fewer than three lines of text below before the page turns"),
    ("runt", "One-word last lines", "a paragraph ending in a single word"),
    ("lone-i", "Lone “I”s at line edges", "too many in a paragraph or on a page"),
    ("starts", "Same word starting lines", "two lines running"),
    ("ends", "Same word ending lines", "two lines running"),
    ("tall-stack", "Word stacked four high", "the same word on four or more lines running, even askew"),
    ("stack", "Word stacked three high", "the same word on three lines running, a little askew"),
    ("above", "Word above itself", "squarely on top of the same word"),
]

#: Stages whose findings are split into groups by kind, and those groups.
_KINDS = {"layout": LAYOUT_GROUPS, "languagetool": LANGUAGETOOL_GROUPS}

#: Reasons that outweigh another dictionary's say-so: macOS accepts
#: "Ziggys" and "practiced", but they are still worth a look.
STRONG_REASONS = {"missing apostrophe?", "capitals differ", "American spelling?"}

_TITLES = {key: (title, blurb) for key, title, blurb in SPELLING_GROUPS}

#: Quoted stretches as the extractor writes them (\say → “…”, \bsq → ‘…’),
#: never running across a paragraph break. Inside single quotes a ’ followed
#: by a letter is an apostrophe (‘there’d be none’), not the closing mark.
_QUOTED = re.compile(r"“[^”\n]*”|‘(?:[^‘’\n]|’(?=\w))*’")

_SENTENCE_END = ".!?\n"


@dataclass
class Item:
    """One row: a misspelt word with all its uses, or one other finding.

    `reason` says in plain words why a word is flagged; for other stages the
    message already does, and it is empty.
    """

    key: str
    stage: str
    word: str | None
    message: str
    note: str
    suggestions: list[str]
    uses: list[Located]
    reason: str = ""
    #: False for a word no word list should take: a command whose backslash
    #: was dropped ("bsqentertainment"), fixed in the source instead.
    addable: bool = True


@dataclass
class Group:
    key: str
    title: str
    blurb: str
    items: list[Item] = field(default_factory=list)
    skipped: str | None = None
    hidden: int = 0  # uses left out because they are marked OK
    section: str = ""  # the stage a sub-group belongs to ("Layout"), shown as a heading


def fold(word: str) -> str:
    """The word without case, hyphens, spaces or accents."""
    plain = unicodedata.normalize("NFKD", word)
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return plain.lower().replace("-", "").replace(" ", "")


#: British forms of American endings: (American pattern, British replacement).
#: A word is "American spelling?" when aspell suggests the British form.
_BRITISH = [
    (re.compile(r"iz(e|es|ed|ing|ation|ations|er|ers)$"), r"is\1"),
    (re.compile(r"or(s|ful|fully|ed|ing|ite|ites|less)?$"), r"our\1"),
    (re.compile(r"ter(s)?$"), r"tre\1"),
    (re.compile(r"og(s)?$"), r"ogue\1"),
    (re.compile(r"ced$"), "sed"),
    (re.compile(r"cing$"), "sing"),
    (re.compile(r"(?<=[a-z])or(?=[a-z]+$)"), "our"),  # colorful, honorable
]


#: The same, the other way: British forms aspell's en_GB dictionary lacks
#: but whose American form it suggests (synthesisers → synthesizers).
_AMERICAN = [
    (re.compile(r"is(e|es|ed|ing|er|ers|ation|ations)$"), r"iz\1"),
    (re.compile(r"our(s|ful|ed|ing|less)?$"), r"or\1"),
    (re.compile(r"(?<=[a-z])our(?=[a-z]+$)"), "or"),
]


def reason(word: str, suggestions: list[str], note: str) -> str:
    """Why `word` is flagged, worked out from aspell's suggestions.

    aspell only ever says "unknown, and here are the nearest words". Most
    of the time the nearest words show what is wrong; this says so plainly.
    """
    if note:
        return note
    lower = {s.replace("’", "'").lower() for s in suggestions}
    if word.endswith("s") and {(word[:-1] + "'s").lower(), (word + "'").lower()} & lower:
        return "missing apostrophe?"
    if word.lower() in lower:
        return "capitals differ"
    if (word + "s").lower() in lower or (word + "es").lower() in lower:
        return "aspell knows only the plural"
    for suggestion in suggestions:
        if fold(suggestion) == fold(word) and suggestion.replace(" ", "").replace("-", "") != suggestion:
            return "usually two words" if " " in suggestion else "usually hyphenated"
    if any(fold(s) == fold(word) for s in suggestions):
        return "accent differs"
    for pattern, british in _BRITISH:
        if pattern.search(word) and pattern.sub(british, word).lower() in lower:
            return "American spelling?"
    for pattern, american in _AMERICAN:
        if pattern.search(word) and pattern.sub(american, word).lower() in lower:
            return "British spelling; aspell knows only the American"
    return "not in the dictionary"


def _macro_slip(word: str, uses: list[Located], source: Source) -> str | None:
    """The command a missing backslash left glued to the word, if any.

    `bsq{entertainment}` without its backslash reads as the word
    "bsqentertainment". The braces in its source give it away.
    """
    for use in uses:
        if "{" in use.text or "}" in use.text:
            for name in KNOWN_COMMANDS:
                if word.startswith(name) and len(word) > len(name):
                    return name
    return None


def _starts_sentence(text: str, at: int) -> bool:
    """True if the word at `at` opens a sentence (quotes and brackets aside)."""
    k = at
    while k > 0 and text[k - 1] in " \t“‘(":
        k -= 1
    return k == 0 or text[k - 1] in _SENTENCE_END


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    """Every quoted stretch, in order (they never overlap)."""
    return [m.span() for m in _QUOTED.finditer(text)]


def _inside(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    """True if [start, end) lies strictly inside one of the sorted `spans`."""
    k = bisect_left(spans, (start,)) - 1
    return k >= 0 and spans[k][0] < start and end < spans[k][1]


def classify(word: str, uses: list[Located], spans: list[tuple[int, int]],
             suggestions: list[str], prose: Prose, source: Source,
             elsewhere: str = "", quoted: list[tuple[int, int]] | None = None) -> tuple[str, str]:
    """The group key for one unknown word, and a note to show beside it.

    `spans` are the word's uses as prose offsets. The rules run in this
    order, first match winning, which is not the order groups are shown in:
    a lower-case "ok" is a variant before it is a typo. Variants come after
    quotes and bold because aspell splits almost anything ("secours" →
    "sec ours"), so a foreign phrase would otherwise pass as a variant.
    `quoted` is `_quoted_spans(prose.text)`, worked out once per run.
    """
    slip = _macro_slip(word, uses, source)
    if slip:
        return "latex", f"missing \\ before \\{slip}?"
    if quoted is None:
        quoted = _quoted_spans(prose.text)
    if all(_inside(quoted, start, end) for start, end in spans):
        return "quotes", ""
    if all(prose.bold[start] for start, _ in spans):
        return "bold", ""
    # `elsewhere` says which larger dictionary knows the word, if any;
    # only a word macOS alone knows is worth a note.
    if elsewhere and reason(word, suggestions, "") not in STRONG_REASONS:
        return LAST, MAC_ONLY if elsewhere == dictionaries.MACOS_ONLY else ""
    if any(fold(s) == fold(word) for s in suggestions):
        return "variants", ""
    if word[0].isupper() and any(not _starts_sentence(prose.text, start) for start, _ in spans):
        return "names", ""
    # Lower-case, or capitalised only because it starts a sentence.
    if suggestions:
        return "typos", ""
    return "other", ""


def _spelling_groups(run: Run, findings: list) -> list[Group]:
    by_word: dict[str, list] = defaultdict(list)
    for finding in findings:
        by_word[finding.group].append(finding)

    groups = {key: Group(key, title, blurb) for key, title, blurb in SPELLING_GROUPS}
    known = run.stats.get("spelling", {}).get("elsewhere", {})
    quoted = _quoted_spans(run.prose.text)
    for word, found in sorted(by_word.items(), key=lambda kv: kv[1][0].start):
        uses = [Located(f, run.prose, run.source) for f in found]
        spans = [(f.start, f.end) for f in found]
        suggestions = found[0].suggestions
        key, note = classify(word, uses, spans, suggestions, run.prose, run.source,
                             known.get(word, ""), quoted)
        why = reason(word, suggestions, note)
        if key == LAST and why == "not in the dictionary":
            why = ""   # it is in one, just not aspell's
        slip = _macro_slip(word, uses, run.source)
        if slip:  # aspell's nearest words ("discontentment") are no help
            suggestions = [f"\\{slip}{{{word[len(slip):]}}}"]
        groups[key].items.append(Item(
            f"spelling:{word}", "spelling", word, word, note, suggestions, uses, why,
            addable=not slip,
        ))
    return [group for group in groups.values() if group.items]


def _drop_ok(groups: list[Group], run: Run, ok: set) -> list[Group]:
    """Leave out every use marked OK; an item with none left goes too."""
    for group in groups:
        kept = []
        for item in group.items:
            uses = [u for u in item.uses
                    if (item.stage, u.text, context_of(run.source, u)) not in ok]
            group.hidden += len(item.uses) - len(uses)
            if uses:
                item.uses = uses
                kept.append(item)
        group.items = kept
    return groups


def group_findings(run: Run, ok: set | frozenset = frozenset()) -> list[Group]:
    """Every stage's findings as groups, in run order, spelling split up.

    `ok` holds the places marked OK (see donelog), which are left out.
    """
    groups = _all_groups(run)
    if not ok:
        return groups
    groups = _drop_ok(groups, run, ok)
    spelling = {key for key, _, _ in SPELLING_GROUPS}
    # A sub-group emptied by OK marks is kept only to carry its hidden
    # count; views show sub-groups with items.
    return [g for g in groups if (g.key not in spelling and not g.section) or g.items or g.hidden]


def _all_groups(run: Run) -> list[Group]:
    """Every group in run order, with the LAST group moved to the end."""
    out = _groups_in_run_order(run)
    last = [g for g in out if g.key == LAST]
    if not last:
        return out
    at = out.index(last[0])
    out.remove(last[0])
    spelling = {key for key, _, _ in SPELLING_GROUPS}
    if not any(g.key in spelling for g in out):
        # Spelling keeps its place, if only to say "nothing found".
        stage = next(s for s, _ in run.results if s.NAME == "spelling")
        out.insert(at, Group(stage.NAME, stage.TITLE, stage.BLURB))
    return [*out, last[0]]


def _groups_in_run_order(run: Run) -> list[Group]:
    out: list[Group] = []
    for stage, outcome in run.results:
        if isinstance(outcome, str):
            out.append(Group(stage.NAME, stage.TITLE, stage.BLURB, skipped=outcome))
            continue
        if stage.NAME == "spelling" and outcome:
            out += _spelling_groups(run, outcome)
            continue
        if stage.NAME in _KINDS and outcome:
            out += _kind_groups(run, stage, outcome)
            continue
        group = Group(stage.NAME, stage.TITLE, stage.BLURB)
        group.items = _items(run, stage.NAME, outcome)
        out.append(group)
    return out


#: Stages whose findings with the same group are one item with several
#: places: the same repeat ("cold cold" in a refrain) is one thing to look at.
_SAME_GROUP_ONE_ITEM = {"repeats"}


def _items(run: Run, stage: str, findings: list) -> list[Item]:
    items: list[Item] = []
    merged: dict[str, Item] = {}
    for f in sorted(findings, key=lambda f: (f.start, f.end)):
        use = Located(f, run.prose, run.source)
        if stage in _SAME_GROUP_ONE_ITEM and f.group in merged:
            merged[f.group].uses.append(use)
            continue
        item = Item(f"{stage}:{f.start}:{f.group}", stage, None, f.message, f.note,
                    f.suggestions, [use])
        items.append(item)
        if stage in _SAME_GROUP_ONE_ITEM and f.group:
            merged[f.group] = item
    return items


def _kind_groups(run: Run, stage, findings: list) -> list[Group]:
    """A stage's findings split by kind (the finding's group), in the order
    the stage's kinds are listed, under the stage's title."""
    out = []
    for kind, title, blurb in _KINDS[stage.NAME]:
        mine = [f for f in findings if f.group == kind]
        if mine:
            out.append(Group(f"{stage.NAME}-{kind}", title, blurb, _items(run, stage.NAME, mine),
                             section=stage.TITLE))
    return out
