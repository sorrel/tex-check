"""Terminal styling shared by the report: colours, headings, paths, plurals.

Widths are always measured on plain text and colour applied afterwards (an
ANSI escape takes no columns). With colour off every style is a no-op.
"""

import os
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


def snippet(source: Source, loc: Located, style: Style, width: int) -> str:
    """The source line around a finding, with the finding highlighted."""
    cut_left, before, hit, after, cut_right = snippet_parts(source, loc, width)
    head = style.dim("…") if cut_left else ""
    tail = style.dim("…") if cut_right else ""
    return f"{head}{before}{style.red(hit)}{after}{tail}"
