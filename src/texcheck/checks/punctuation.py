"""Stage 2: spacing and punctuation.

Double spaces, a space before a comma or full stop, doubled or clashing marks
(",," ".," ".."), a missing space after a mark, and unbalanced or badly
spaced brackets.

Double spaces are only reported where they really sit side by side in the
source, not where removing a command happened to leave two spaces. TeX
collapses them in the PDF anyway, so they are tidiness, not errors in print.
"""

import re

from ..findings import Finding
from ..prose import paragraphs

NAME = "punctuation"
TITLE = "Spacing and punctuation"
BLURB = "double spaces, stray or doubled marks, brackets"

# Words that end in a full stop without ending a sentence.
ABBREVIATIONS = {
    "etc", "eg", "ie", "vs", "cf", "al", "approx", "st", "mr", "mrs", "ms",
    "dr", "prof", "no", "nos", "vol", "pp", "ch", "fig", "jr", "sr", "rd",
    "ave", "co", "ltd", "inc", "rev", "sgt", "capt", "col", "gen", "lt",
    "mt", "ft", "oz", "lb", "am", "pm",
}

RULES = [
    # (pattern, message) — the finding covers group 1 if present, else the whole match.
    (re.compile(r"(?<=[^\W_])([ \t]+)(?=[,;:]|[!?](?![^\W\d_])|\.(?![.\d]))"), "space before punctuation"),
    (re.compile(r",{2,}|;{2,}|:{2,}"), "doubled punctuation"),
    (re.compile(r"(?<!\.)\.\.(?!\.)"), "two full stops (one, or an ellipsis?)"),
    (re.compile(r"\.{4,}"), "more than three dots"),
    (re.compile(r",[;:.!?]|;[,:.!?]|:[,;.!?]"), "clashing punctuation"),
    (re.compile(r"[!?]\.(?!\.)"), "full stop after ! or ?"),
    (re.compile(r"(?<=[a-z])([,;])(?=[A-Za-z])"), "no space after punctuation"),
    (re.compile(r"(?<=[a-z]{2})([.!?])(?=[A-Z][a-z])"), "no space after sentence end"),
    # "to\textbf{The}" prints as "toThe": a lower-case word running into a capitalised one.
    (re.compile(r"(?<![\w'’])[a-z]+[A-Z][a-z]+"), "words run together (missing space?)"),
    (re.compile(r"\(([ \t]+)"), "space after opening bracket"),
    (re.compile(r"(?<=\S)([ \t]+)\)"), "space before closing bracket"),
]

DOUBLE_SPACE = re.compile(r"(?<=\S)[ \t]{2,}(?=\S)")
FULL_STOP_COMMA = re.compile(r"([^\W\d_]+)\.[,;]")


def run(prose, settings) -> list[Finding]:
    found = []
    for base, para in paragraphs(prose.text):
        found += [Finding(NAME, base + m.start(), base + m.end(), "double space")
                  for m in DOUBLE_SPACE.finditer(para)
                  if prose.is_contiguous(base + m.start(), base + m.end())]
        for pattern, message in RULES:
            g = 1 if pattern.groups else 0  # the rule's own span, if it marks one
            found += [Finding(NAME, base + m.start(g), base + m.end(g), message)
                      for m in pattern.finditer(para)]

        # ".," is fine after an abbreviation ("etc.,", "e.g.,"), otherwise a slip.
        for m in FULL_STOP_COMMA.finditer(para):
            word = m.group(1)
            dotted = m.start() > 0 and para[m.start() - 1] == "."
            if word.lower() not in ABBREVIATIONS and len(word) > 1 and not dotted:
                found.append(Finding(NAME, base + m.end(1), base + m.end(), "full stop and comma"))

        found += unbalanced_brackets(para, base)
    return found


def unbalanced_brackets(para: str, base: int) -> list[Finding]:
    pairs = {")": "(", "]": "["}
    stack: list[tuple[str, int]] = []
    found = []
    for k, ch in enumerate(para):
        if ch in "([":
            stack.append((ch, k))
        elif ch in ")]":
            if stack and stack[-1][0] == pairs[ch]:
                stack.pop()
            else:
                found.append(Finding(NAME, base + k, base + k + 1, f"unmatched “{ch}”"))
    for ch, k in stack:
        found.append(Finding(NAME, base + k, base + k + 1, f"unclosed “{ch}”"))
    return found
