"""Stage 4: grammar, by rule.

A small set of patterns for mistakes that are nearly always wrong and that a
spelling checker cannot see, because every word is a real word: "a apple",
"could of", "more then", "its a", "your welcome", a lower-case "i", a
sentence that starts in lower case.

These are heuristics: each finding is a prompt to look, not a verdict. A full
grammar checker (LanguageTool) could be added as a further stage later.
"""

import re

from ..findings import Finding
from ..prose import paragraphs
from .punctuation import ABBREVIATIONS

NAME = "grammar"
TITLE = "Grammar (rule-based)"
BLURB = "a/an, could of, then/than, its/it's and more"

# Words that start with a vowel letter but a consonant sound: "a unicorn", "a one-off".
VOWEL_LETTER_CONSONANT_SOUND = (
    "uni", "use", "usu", "usa", "uti", "ute", "ure", "uro", "ura", "eu", "ewe",
    "one", "once", "ubiq", "ufo", "uk", "ouija",
)
# Words that start with a consonant letter but a vowel sound: "an hour".
SILENT_H = ("hour", "honest", "honour", "honor", "heir", "herb")


def a_before_vowel(m) -> str | None:
    word = m.group(2)
    if word.isupper() or word.lower().startswith(VOWEL_LETTER_CONSONANT_SOUND):
        return None
    return f"“{m.group(1)} {word}”: should it be “an”?"


def an_before_consonant(m) -> str | None:
    word = m.group(2)
    # Acronyms read letter by letter ("an LP", "an MP") take "an".
    if word.isupper() or word.lower().startswith(SILENT_H):
        return None
    return f"“{m.group(1)} {word}”: should it be “a”?"


def lower_after_full_stop(m) -> str | None:
    if m.group(1).lower() in ABBREVIATIONS:
        return None
    return f"“{m.group(3)}” after a full stop: capital letter?"


RULES = [
    (re.compile(r"\b([Aa])\s+([aeiouAEIOU][\w'’-]*)"), a_before_vowel),
    (re.compile(r"\b([Aa]n)\s+([b-df-hj-np-tv-zB-DF-HJ-NP-TV-Z][\w'’-]*)"), an_before_consonant),
    (re.compile(r"\b(?:could|should|would|must|might)\s+of\b", re.IGNORECASE),
     lambda m: f"“{m.group()}”: should it be “… have”?"),
    (re.compile(r"\b(?:more|less|better|worse|rather|bigger|smaller|older|younger|"
                r"greater|fewer|higher|lower|faster|slower|longer|shorter|"
                r"easier|harder|other)\s+then\b", re.IGNORECASE),
     lambda m: f"“{m.group()}”: should it be “than”?"),
    (re.compile(r"\bits\s+(?:a|an|the|not|been|going|gone|got|so|too|very|never|always)\b"),
     lambda m: f"“{m.group()}”: should it be “it's”?"),
    (re.compile(r"\bit['’]s\s+own\b", re.IGNORECASE), lambda m: "“it's own”: should it be “its own”?"),
    (re.compile(r"\byour\s+(?:a|an|the|welcome|going|not)\b", re.IGNORECASE),
     lambda m: f"“{m.group()}”: should it be “you're”?"),
    (re.compile(r"\b(her|your|their|our)['’]s\b", re.IGNORECASE),
     lambda m: f"“{m.group()}”: possessives take no apostrophe (“{m.group(1)}s”)"),
    (re.compile(r"\b(?:a|an|the)\s+(?:a|an|the)\b"), lambda m: f"“{m.group()}”: two articles"),
    (re.compile(r"(?<![\w'’.-])i(?![\w'’.-])"), lambda m: "lower-case “i”"),
    (re.compile(r"\b([A-Za-z][a-z]+)(\.)\s+([a-z][\w'’-]*)"), lower_after_full_stop),
]


def run(prose, settings) -> list[Finding]:
    found = []
    for base, para in paragraphs(prose.text):
        for pattern, judge in RULES:
            for m in pattern.finditer(para):
                message = judge(m)
                if message:
                    found.append(Finding(NAME, base + m.start(), base + m.end(), message))
    return found
