"""Small helpers on typeset words shared by the layout modules."""

import re

from ...pdfwords import Line, Word, lines_of

#: A word: letters, with inner apostrophes (don't, Ziggy’s).
TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def normal(token: str) -> str:
    """A token as compared: straight apostrophe, lower case."""
    return token.replace("’", "'").lower()


def key(word: Word) -> str:
    """The word for comparing, or "" if it is not exactly one word."""
    tokens = TOKEN.findall(word.text)
    return normal(tokens[0]) if len(tokens) == 1 else ""


def shown(word: Word) -> str:
    """The word as written, without its punctuation: “I”, not “i”."""
    tokens = TOKEN.findall(word.text)
    return tokens[0] if tokens else word.text


def body(words: list[Word]) -> list[Line]:
    """A page's lines, without page numbers."""
    return [ln for ln in lines_of(words)
            if not (len(ln) == 1 and ln[0].text.strip("()[]").isdigit())]
