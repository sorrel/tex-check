"""Sort findings into groups, so the likely mistakes come first.

A book's spelling findings are mostly not mistakes: foreign phrases, dialect
in dialogue, names, words aspell knows only in another form. Left in one
list, the few real typos are buried. So each unknown word is put in a group,
judged from all its uses, and the groups are shown likely typos first.

The rules are heuristics, an aid to reading and not a verdict; `classify`
says which wins when several apply. Stages other than spelling keep one
group each, in the order they run.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

from .prose import KNOWN_COMMANDS, Prose, Source
from .run import Located, Run

#: Spelling's groups, in the order they are shown.
SPELLING_GROUPS = [
    ("typos", "Likely typos", "words aspell can correct, not names"),
    ("other", "Other unknown words", "aspell has no suggestion"),
    ("quotes", "In quotations", "dialogue, dialect and quoted words"),
    ("bold", "Foreign and bold phrases", "set in bold, often not English"),
    ("names", "Names", "capitalised mid-sentence"),
    ("variants", "Variants", "known in another case, spacing or accent"),
]

_TITLES = {key: (title, blurb) for key, title, blurb in SPELLING_GROUPS}

#: Quoted stretches as the extractor writes them (\say → “…”, \bsq → ‘…’),
#: never running across a paragraph break. Inside single quotes a ’ followed
#: by a letter is an apostrophe (‘there’d be none’), not the closing mark.
_QUOTED = re.compile(r"“[^”\n]*”|‘(?:[^‘’\n]|’(?=\w))*’")

_SENTENCE_END = ".!?\n"


@dataclass
class Item:
    """One row: a misspelt word with all its uses, or one other finding."""

    key: str
    stage: str
    word: str | None
    message: str
    note: str
    suggestions: list[str]
    uses: list[Located]


@dataclass
class Group:
    key: str
    title: str
    blurb: str
    items: list[Item] = field(default_factory=list)
    skipped: str | None = None


def fold(word: str) -> str:
    """The word without case, hyphens, spaces or accents."""
    plain = unicodedata.normalize("NFKD", word)
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return plain.lower().replace("-", "").replace(" ", "")


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


def _starts_sentence(prose: Prose, at: int) -> bool:
    before = prose.text[:at].rstrip(" \t“‘(")
    return not before or before[-1] in _SENTENCE_END


def classify(word: str, uses: list[Located], spans: list[tuple[int, int]],
             suggestions: list[str], prose: Prose, source: Source) -> tuple[str, str]:
    """The group key for one unknown word, and a note to show beside it.

    `spans` are the word's uses as prose offsets. The rules run in this
    order, first match winning, which is not the order groups are shown in:
    a lower-case "ok" is a variant before it is a typo. Variants come after
    quotes and bold because aspell splits almost anything ("secours" →
    "sec ours"), so a foreign phrase would otherwise pass as a variant.
    """
    slip = _macro_slip(word, uses, source)
    if slip:
        return "typos", f"missing \\ before \\{slip}?"
    quoted = [m.span() for m in _QUOTED.finditer(prose.text)]
    if all(any(a < start and end < b for a, b in quoted) for start, end in spans):
        return "quotes", ""
    if all(prose.bold[start] for start, _ in spans):
        return "bold", ""
    if any(fold(s) == fold(word) for s in suggestions):
        return "variants", ""
    if word[0].isupper() and any(not _starts_sentence(prose, start) for start, _ in spans):
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
    for word, found in sorted(by_word.items(), key=lambda kv: kv[1][0].start):
        uses = [Located(f, run.prose, run.source) for f in found]
        spans = [(f.start, f.end) for f in found]
        key, note = classify(word, uses, spans, found[0].suggestions, run.prose, run.source)
        groups[key].items.append(
            Item(f"spelling:{word}", "spelling", word, word, note, found[0].suggestions, uses)
        )
    return [group for group in groups.values() if group.items]


def group_findings(run: Run) -> list[Group]:
    """Every stage's findings as groups, in run order, spelling split up."""
    out: list[Group] = []
    for stage, outcome in run.results:
        if isinstance(outcome, str):
            out.append(Group(stage.NAME, stage.TITLE, stage.BLURB, skipped=outcome))
            continue
        if stage.NAME == "spelling" and outcome:
            out += _spelling_groups(run, outcome)
            continue
        group = Group(stage.NAME, stage.TITLE, stage.BLURB)
        for finding in sorted(outcome, key=lambda f: (f.start, f.end)):
            group.items.append(Item(
                f"{stage.NAME}:{finding.start}", stage.NAME, None, finding.message,
                finding.note, finding.suggestions, [Located(finding, run.prose, run.source)],
            ))
        out.append(group)
    return out
