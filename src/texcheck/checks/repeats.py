"""Stage 1: the same word twice in a row ("the the").

Only whitespace may separate the two words, so "no, no" and "baby / baby"
across a lyric line break are left alone. The check runs across LaTeX markup
("the \\textbf{the}") and across source line breaks within a paragraph.
"""

import re

from ..findings import Finding
from ..prose import paragraphs

NAME = "repeats"
TITLE = "Repeated words"
BLURB = "the same word twice in a row"

WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")

# Pairs that are often correct English, flagged with a softer note.
OFTEN_FINE = {"had", "that", "is", "do", "can", "very", "so", "no", "bye", "ha", "knock"}


def is_bold_name(prose, first: int, second: int) -> bool:
    """Both words bold and capitalised: a name such as Duran Duran or The The."""
    text = prose.text
    return all(prose.bold[k] and text[k].isupper() for k in (first, second))


def run(prose, settings) -> list[Finding]:
    found = []
    for base, para in paragraphs(prose.text):
        previous = None
        for match in WORD.finditer(para):
            if (
                previous is not None
                and match.group().lower() == previous.group().lower()
                and not para[previous.end() : match.start()].strip()
                and not is_bold_name(prose, base + previous.start(), base + match.start())
            ):
                word = match.group().lower()
                found.append(
                    Finding(
                        NAME,
                        base + previous.start(),
                        base + match.end(),
                        f"“{previous.group()} {match.group()}”",
                        note="can be correct" if word in OFTEN_FINE else "",
                    )
                )
            previous = match
    return found
