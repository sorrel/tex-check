"""Stage 6: LanguageTool, a full grammar and style checker, run on this Mac.

It catches what patterns cannot: "I didn't understood", "would have
succeed", "these kind of", "told them all it's name", a noun "license".
See languagetool.py for how the local server is started; nothing leaves
the machine.

Its findings are shown in four groups (`KINDS`), likely mistakes first.
Rules that duplicate another stage are turned off: spelling (aspell),
"the the" (repeats), doubled spaces (punctuation), and Oxford -ize
spelling, which the house -ise dictionary contradicts. Matches wholly in
bold are dropped: house style bolds names and titles.

Tuned on a 106,000-word book (25 November 2026): 893 matches, about 60
grammar and typos, 30 British usage, 70 hyphens and accents, the rest
commas and style (281 of them "comma before and").

In verse (lines under prose.VERSE_LINE words) a poet's choices are left
alone: style suggestions (VERSE_FREE categories: "summertime" → "summer"),
comma suggestions, lower-case line starts, and brackets or quotes "unpaired"
because they close lines later (the punctuation stage pairs those). Mistakes
stay: grammar, typos, doubled marks (",,"), spacing.
"""

from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor

from .. import languagetool
from ..findings import Finding, Skipped
from ..prose import BREAK, verse_spans

NAME = "languagetool"
TITLE = "LanguageTool"
BLURB = "grammar, usage and style, checked on this Mac"

#: The groups, in the order they are shown: (kind, title, blurb).
KINDS = [
    ("grammar", "Grammar and typos", "wrong verb forms, confused words, missing words"),
    ("british", "British usage", "American spellings and words"),
    ("hyphens", "Hyphens, compounds and accents", "twenty-year-old, hitchhiked, café"),
    ("style", "Commas and style", "suggestions more than mistakes"),
]

DISABLED_RULES = (
    "MORFOLOGIK_RULE_EN_GB",       # spelling: aspell's job
    "ENGLISH_WORD_REPEAT_RULE",    # "the the": the repeats stage
    "WHITESPACE_RULE",             # doubled spaces: punctuation, and TeX collapses them
)
DISABLED_CATEGORIES = (
    "BRE_STYLE_OXFORD_SPELLING",   # -ize; the house dictionary is en_GB-ise
    "MULTITOKEN_SPELLING",         # names ("Franz Klammer" → "Franz Krommer"): spelling's job
)

#: Characters per request, cut at a paragraph break. One request per 20,000
#: characters keeps each answer quick; a few run at once.
CHUNK = 20_000
AT_ONCE = 4

_STYLE_CATEGORIES = {"PUNCTUATION", "REPETITIONS_STYLE", "STYLE", "REDUNDANCY",
                     "PLAIN_ENGLISH", "WIKIPEDIA", "CREATIVE_WRITING", "TEXT_ANALYSIS"}


#: Suggestions, not mistakes: dropped in verse.
VERSE_FREE = {"STYLE", "REDUNDANCY", "PLAIN_ENGLISH", "WIKIPEDIA", "CREATIVE_WRITING",
              "TEXT_ANALYSIS", "REPETITIONS_STYLE"}


def free_in_verse(rule: str, category: str) -> bool:
    """Whether a rule's match is a poet's choice when it falls in verse."""
    return (category in VERSE_FREE
            or rule == "UPPERCASE_SENTENCE_START"
            or "UNPAIRED" in rule
            or (category == "PUNCTUATION" and "COMMA" in rule))


#: Rules in a style category that find slips, not choices: shown with grammar.
_MISTAKES = {"DOUBLE_PUNCTUATION"}


def kind_of(rule: str, category: str) -> str:
    """Which group a rule's matches go in. Unknown rules count as grammar:
    better seen first than lost among the commas."""
    if category == "AMERICAN_ENGLISH" or rule.startswith("EN_GB_"):
        return "british"
    if (category in ("COMPOUNDING", "TYPOGRAPHY")
            or any(part in rule for part in ("HYPHEN", "COMPOUNDS", "DIACRITIC"))):
        return "hyphens"
    if category in _STYLE_CATEGORIES and rule not in _MISTAKES:
        return "style"
    return "grammar"


def run(prose, settings) -> list[Finding]:
    text = prose.text
    chunks = list(_chunks(text))
    settings.progress("LanguageTool: starting its server on this Mac")
    try:
        languagetool.server()
        settings.progress(f"LanguageTool: checking {len(text):,} characters")
        with ThreadPoolExecutor(AT_ONCE) as pool:
            answers = list(pool.map(lambda chunk: _check(text[chunk[0]:chunk[1]]), chunks))
    except languagetool.Unavailable as err:
        raise Skipped(str(err)) from err
    found = []
    verse = verse_spans(text)
    for (base, _), matches in zip(chunks, answers, strict=True):
        for m in matches:
            start = base + m["offset"]
            end = start + m["length"]
            if end <= start or all(prose.bold[start:end]):
                continue
            rule = m["rule"]
            if free_in_verse(rule["id"], rule["category"]["id"]) and _within(verse, start):
                continue
            found.append(Finding(
                NAME, start, end, m["message"],
                suggestions=[r["value"] for r in m["replacements"][:3]],
                group=kind_of(rule["id"], rule["category"]["id"]),
            ))
    return found


def _within(spans: list[tuple[int, int]], at: int) -> bool:
    k = bisect_right(spans, (at, float("inf"))) - 1
    return k >= 0 and spans[k][0] <= at < spans[k][1]


def _check(text: str) -> list[dict]:
    return languagetool.check(text, "en-GB", DISABLED_RULES, DISABLED_CATEGORIES)


def _chunks(text: str):
    """(start, end) pieces of at most about CHUNK characters, each ending at
    a paragraph break so no sentence is cut, and none starting with one."""
    start = 0
    while start < len(text):
        while text.startswith(BREAK, start) or text.startswith("\n", start):
            start += 1
        if start >= len(text):
            return
        end = len(text) if len(text) - start <= CHUNK else text.rfind(BREAK, start + 1, start + CHUNK)
        if end <= start:   # one paragraph longer than CHUNK: send it whole
            end = text.find(BREAK, start + CHUNK)
            end = len(text) if end == -1 else end
        yield start, end
        start = end
