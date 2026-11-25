"""Checkable prose that never loses track of where it came from.

The checks never see LaTeX. They see a `Prose` object (written by latex.py):
plain text in which every character remembers the offset of the source
character it came from. That lets a check run simple regexes over clean
English and still report the true line and column in the .tex file.
"""

import re
from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Self

BREAK = "\n\n"  # a paragraph break in the extracted prose


@dataclass
class Prose:
    """Extracted text, with a source offset (and a bold flag) per character."""

    chars: list[str] = field(default_factory=list)
    offsets: list[int] = field(default_factory=list)
    bold: list[bool] = field(default_factory=list)
    #: Spans of section and chapter titles, for the layout checks.
    titles: list[tuple[int, int]] = field(default_factory=list)
    #: Of those, the spans of \part titles (each part's own page).
    parts: list[tuple[int, int]] = field(default_factory=list)
    #: `text`, joined once and kept until the next change.
    _text: str | None = field(default=None, init=False, repr=False, compare=False)

    def put(self, text: str, offset: int, bold: bool = False) -> None:
        """Append `text`, every character of it from source `offset`."""
        self.chars.extend(text)
        self.offsets.extend([offset] * len(text))
        self.bold.extend([bold] * len(text))
        self._text = None

    def put_run(self, text: str, start: int, bold: bool = False) -> None:
        """Append `text`, copied straight from the source at `start`."""
        self.chars.extend(text)
        self.offsets.extend(range(start, start + len(text)))
        self.bold.extend([bold] * len(text))
        self._text = None

    def extend(self, other: Self) -> None:
        """Append another Prose (a footnote), keeping its title spans."""
        shift = len(self.chars)
        self.titles += [(a + shift, b + shift) for a, b in other.titles]
        self.parts += [(a + shift, b + shift) for a, b in other.parts]
        self.chars += other.chars
        self.offsets += other.offsets
        self.bold += other.bold
        self._text = None

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = "".join(self.chars)
        return self._text

    def source_span(self, start: int, end: int) -> tuple[int, int]:
        """Map a [start, end) span of the prose to a span of the source."""
        end = max(end, start + 1)
        return self.offsets[start], self.offsets[end - 1] + 1

    def is_contiguous(self, start: int, end: int) -> bool:
        """True if prose[start:end] sits unbroken in the source too."""
        return all(self.offsets[k + 1] == self.offsets[k] + 1 for k in range(start, end - 1))


class Source:
    """The original file, for turning offsets into lines, columns and snippets."""

    def __init__(self, text: str, path: str = ""):
        self.text = text
        self.path = path
        self.line_starts = [0, *(m.end() for m in re.finditer("\n", text))]

    def line_col(self, offset: int) -> tuple[int, int]:
        """1-based line and column of a source offset."""
        line = bisect_right(self.line_starts, offset) - 1
        return line + 1, offset - self.line_starts[line] + 1

    def line_text(self, line: int) -> str:
        """The text of a 1-based line, without its newline."""
        start = self.line_starts[line - 1]
        end = self.text.find("\n", start)
        return self.text[start:] if end == -1 else self.text[start:end]


_PARAGRAPH = re.compile(r"(?:[^\n]|\n(?![ \t]*\n))+")


def paragraphs(text: str) -> Iterator[tuple[int, str]]:
    """Yield (offset, paragraph) for each run of text between blank lines."""
    for m in _PARAGRAPH.finditer(text):
        if m.group().strip():
            yield m.start(), m.group()
