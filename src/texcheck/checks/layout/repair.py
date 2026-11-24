"""Split words PDFKit ran together ("ingintothenight,") with the book's
own vocabulary. Some lines come back with touching letter boxes and no
gaps, so their words cannot be told apart by position."""

import re

from ...pdfwords import Word
from .words import TOKEN, normal

#: Shorter "words" are left alone: real run-togethers are long.
MIN_GLUED = 12
_OPENING = set("“‘([")
_PARTS = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*|\d+|[^\w]")


def unglue(pages: list[list[Word]], vocab: set[str]) -> list[list[Word]]:
    """Every page with its run-together words split, sharing out each one's
    width by letter count (its letters' boxes touch, so there is no better
    guide)."""
    return [[piece for word in words for piece in _unglue_word(word, vocab)] for words in pages]


def _unglue_word(word: Word, vocab: set[str]) -> list[Word]:
    parts = split_glued(word.text, vocab) if len(word.text) >= MIN_GLUED else [word.text]
    if len(parts) == 1:
        return [word]
    per = (word.x1 - word.x0) / sum(map(len, parts))
    out, x = [], word.x0
    for n, part in enumerate(parts):
        end = word.x1 if n == len(parts) - 1 else x + per * len(part)
        out.append(Word(part, round(x, 1), round(end, 1), word.y))
        x = end
    return out


def split_glued(text: str, vocab: set[str]) -> list[str]:
    """The words of a run-together "word", or [text] if it is one word.
    Punctuation stays on the word it belongs to; a hyphen joins the next
    piece to the last word."""
    words: list[str] = []
    prefix = ""      # opening marks waiting for the next word
    join = False     # after a hyphen: the next piece continues the last word
    for part in _PARTS.findall(text):
        if TOKEN.fullmatch(part):
            pieces = [part] if normal(part) in vocab else segment(part, vocab)
            if join and words:
                words[-1] += pieces.pop(0)
            if pieces:
                pieces[0] = prefix + pieces[0]
                prefix = ""
            words += pieces
            join = False
        elif part in _OPENING or not words:
            prefix += part
        else:
            words[-1] += part
            join = join or part == "-"
    if prefix:
        words.append(prefix)
    return words if len(words) > 1 else [text]


def segment(letters: str, vocab: set[str]) -> list[str]:
    """`letters` cut into words of `vocab`, as few as possible.

    A piece not in the vocabulary (the tail of a word hyphenated on the line
    above) is allowed but costs more the longer it is, so real words always
    win. Dynamic programming over end positions, words up to 30 letters.
    """
    lower = normal(letters)
    size = len(lower)
    cost = [0.0] + [float("inf")] * size
    back = [0] * (size + 1)
    for end in range(1, size + 1):
        for start in range(max(0, end - 30), end):
            length = end - start
            step = 1 if lower[start:end] in vocab else (2 + length if length <= 15 else float("inf"))
            if cost[start] + step < cost[end]:
                cost[end], back[end] = cost[start] + step, start
    pieces, end = [], size
    while end:
        pieces.append(letters[back[end]:end])
        end = back[end]
    return pieces[::-1]
