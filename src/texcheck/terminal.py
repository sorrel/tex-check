"""Terminal styling shared by the report: colours, headings, paths, plurals.

Widths are always measured on plain text and colour applied afterwards (an
ANSI escape takes no columns). With colour off every style is a no-op.
"""

import os
from itertools import pairwise
from pathlib import Path

from .prose import Source
from .run import Located, snippet_parts


class Style:
    """ANSI styles, or plain text when `colour` is off (piped, --json)."""

    def __init__(self, colour: bool):
        self.colour = colour

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.colour and text else text

    def bold(self, t: str) -> str: return self._wrap("1", t)
    def dim(self, t: str) -> str: return self._wrap("2", t)
    def red(self, t: str) -> str: return self._wrap("1;91", t)
    def yellow(self, t: str) -> str: return self._wrap("93", t)
    def cyan(self, t: str) -> str: return self._wrap("96", t)
    def green(self, t: str) -> str: return self._wrap("92", t)
    def underline(self, t: str) -> str: return self._wrap("4;1", t)

    def count(self, n: int):
        """The colour for a count: green for none, yellow otherwise."""
        return self.green if n == 0 else self.yellow


def plural(n: int, word: str) -> str:
    """"1 word", "2 words"."""
    return f"{n} {word}{'' if n == 1 else 's'}"


def display_path(path: Path, cwd: Path) -> str:
    """`path` relative to `cwd` when it lies inside it, else absolute.
    (abspath, not resolve: a symlinked folder keeps the name you typed.)"""
    absolute = Path(os.path.abspath(path))  # noqa: PTH100
    try:
        return str(absolute.relative_to(os.path.abspath(cwd)))  # noqa: PTH100
    except ValueError:
        return str(absolute)


def heading(title: str, blurb: str, count: str, style: Style, width: int, colour=None) -> str:
    """`Title  blurb ───────── count`, filling the width."""
    plain_left = f"{title}  {blurb} "
    plain_right = f" {count}"
    rule = "─" * max(3, width - len(plain_left) - len(plain_right))
    colour = colour or style.yellow
    return f"{style.bold(title)}  {style.dim(blurb)} {style.dim(rule)} {colour(count)}"


def snippet(source: Source, loc: Located, style: Style, width: int, lines: int = 2) -> list[str]:
    """The source line around a finding, the finding highlighted, wrapped
    at spaces onto at most `lines` lines of `width` columns."""
    cut_left, before, hit, after, cut_right = snippet_parts(source, loc, width * lines - 2)
    head, tail = ("…" if cut_left else ""), ("…" if cut_right else "")
    plain = head + before + hit + after + tail
    hit_at = len(head + before)
    hit_end = hit_at + len(hit)
    out, start = [], 0
    while start < len(plain):
        end = len(plain) if len(plain) - start <= width else plain.rfind(" ", start + 1, start + width + 1)
        if hit_at < end < hit_end and start < hit_at - 1 and plain[hit_at - 1] == " ":
            end = hit_at - 1   # keep the finding whole on one line
        if end <= start:
            end = start + width
        out.append(_styled(plain, start, end, hit_at, hit_end, len(head), len(plain) - len(tail), style))
        start = end + (end < len(plain) and plain[end] == " ")
    return out


def _styled(plain: str, start: int, end: int, hit_at: int, hit_end: int,
            body_at: int, tail_at: int, style: Style) -> str:
    """plain[start:end] with the ellipses dim and the finding red: cut by
    position in the plain text, so a wrap may fall anywhere."""
    marks = sorted({start, end, *(m for m in (body_at, hit_at, hit_end, tail_at) if start < m < end)})
    parts = []
    for a, b in pairwise(marks):
        piece = plain[a:b]
        if a < body_at or a >= tail_at:
            piece = style.dim(piece)
        elif hit_at <= a < hit_end:
            piece = style.red(piece)
        parts.append(piece)
    return "".join(parts)
