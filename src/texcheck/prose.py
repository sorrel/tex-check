"""Turn LaTeX source into checkable prose without losing track of where it came from.

The checks never see LaTeX. They see a `Prose` object: plain text in which
every character remembers the offset of the source character it came from.
That lets a check run simple regexes over clean English and still report the
true line and column in the .tex file.

What the extractor does with the source:

* Only the body is read (between \\begin{document} and \\end{document}).
* Comments, maths and verbatim-like environments are dropped.
* Commands vanish, but the text in their arguments stays, so
  "the \\textbf{the}" still reads as "the the". Commands whose arguments are
  not prose (\\label, \\vspace, \\setcounter, ...) lose their arguments too.
* Footnotes are lifted out and checked as paragraphs of their own, so the
  sentence they interrupt stays whole.
* Line breaks (\\\\), headings, environments and list items become paragraph
  breaks (a blank line), which stops checks from joining lyric lines or a
  heading to the paragraph after it.
* \\say{..} and \\bsq{..} become curly double and single quotes.

Text set in \\textbf (and similar) is marked "bold". The spelling stage uses
that to skip bold names of bands, people and places.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field

BREAK = "\n\n"  # a paragraph break in the extracted prose

# ── How individual commands are treated ─────────────────────────────────────
# Commands not listed anywhere here vanish, and any {group} after them is read
# as ordinary text. That default suits \emph, \textit, \section-like macros,
# and most of a document's own \newcommand definitions.

# Commands whose first N brace arguments are not prose and are thrown away.
DROP_ARGS = {
    "label": 1, "ref": 1, "pageref": 1, "eqref": 1, "cite": 1, "citep": 1,
    "citet": 1, "nocite": 1, "includegraphics": 1, "input": 1, "include": 1,
    "usepackage": 1, "url": 1, "href": 1, "hyperref": 1, "index": 1,
    "hyphenation": 1, "vspace": 1, "hspace": 1, "vskip": 0, "pagestyle": 1,
    "thispagestyle": 1, "pagenumbering": 1, "chapterstyle": 1,
    "setsecheadstyle": 1, "setbeforesecskip": 1, "setaftersecskip": 1,
    "setheadfoot": 2, "setcounter": 2, "addtocounter": 2, "setlength": 2,
    "addtolength": 2, "newcommand": 2, "renewcommand": 2, "providecommand": 2,
    "fontsize": 2, "color": 1, "textcolor": 1, "colorbox": 1, "pagecolor": 1,
    "emoji": 1, "rule": 2, "raisebox": 1, "resizebox": 2, "scalebox": 1,
    "makebox": 0, "parbox": 1, "settowidth": 2, "def": 0,
}

# Commands whose argument is set off from the running text, like a heading.
HEADINGS = {
    "part", "chapter", "section", "subsection", "subsubsection", "paragraph",
    "subparagraph", "caption", "title", "author", "date", "attrib",
    "itattrib", "epigraph",
}

# Of those, the ones that are titles rather than text set apart (an epigraph).
TITLES = {
    "part", "chapter", "section", "subsection", "subsubsection", "paragraph",
    "subparagraph", "title",
}

# Commands whose argument is a footnote-like aside, checked separately.
NOTES = {"footnote", "footnotetext", "marginpar", "endnote"}

# Commands that produce a break in the text.
BREAKS = {
    "par", "newline", "linebreak", "newpage", "clearpage", "cleardoublepage",
    "pagebreak", "item", "bigbreak", "medbreak", "smallbreak", "bigskip",
    "medskip", "smallskip", "vfill", "blankpage", "maketitle",
    "tableofcontents", "mainmatter", "frontmatter", "backmatter",
}

# Commands whose argument is printed in bold: proper names, in this house style.
BOLD = {"textbf", "italic", "textsc"}

# Commands that wrap their argument in quotation marks.
QUOTES = {"say": ("“", "”"), "bsq": ("‘", "’"), "enquote": ("“", "”")}

# Commands that stand for a piece of text.
MACROS = {
    "ldots": "…", "dots": "…", "textellipsis": "…", "LaTeX": "LaTeX",
    "TeX": "TeX", "copyright": "©", "textendash": "–", "textemdash": "—",
    "textquoteright": "’", "textquoteleft": "‘", "ss": "ß", "ae": "æ",
    "oe": "œ", "AE": "Æ", "OE": "Œ", "o": "ø", "O": "Ø", "aa": "å", "l": "ł",
    "pounds": "£", "textpounds": "£", "euro": "€", "S": "§", "P": "¶",
}

#: Every command the extractor knows by name, three letters or more. Used to
#: spot a missing backslash (`bsq{word}` read as "bsqword"); single letters
#: such as \o would match the start of half the dictionary.
KNOWN_COMMANDS = frozenset(
    name for name in (*DROP_ARGS, *HEADINGS, *NOTES, *BREAKS, *BOLD, *QUOTES, *MACROS)
    if len(name) >= 3 and name.isalpha()
)

# Environments whose whole content is skipped.
SKIP_ENVS = {
    "verbatim", "Verbatim", "lstlisting", "minted", "comment", "equation",
    "equation*", "align", "align*", "gather", "gather*", "multline",
    "multline*", "displaymath", "math", "tikzpicture", "picture",
}

# Environments that take non-prose arguments after \begin{..}.
ENV_ARGS = {
    "tabular": 1, "tabular*": 2, "tabularx": 2, "longtable": 1, "minipage": 1,
    "multicols": 1, "multicols*": 1, "wrapfigure": 2, "adjustwidth": 2,
    "list": 2,
}


@dataclass
class Prose:
    """Extracted text, with a source offset (and a bold flag) per character."""

    chars: list[str] = field(default_factory=list)
    offsets: list[int] = field(default_factory=list)
    bold: list[bool] = field(default_factory=list)
    #: Spans of section and chapter titles, for the layout checks.
    titles: list[tuple[int, int]] = field(default_factory=list)

    def put(self, text: str, offset: int, bold: bool = False) -> None:
        for ch in text:
            self.chars.append(ch)
            self.offsets.append(offset)
            self.bold.append(bold)

    def extend(self, other: Prose) -> None:
        shift = len(self.chars)
        self.titles += [(a + shift, b + shift) for a, b in other.titles]
        self.chars += other.chars
        self.offsets += other.offsets
        self.bold += other.bold

    @property
    def text(self) -> str:
        return "".join(self.chars)

    def source_span(self, start: int, end: int) -> tuple[int, int]:
        """Map a [start, end) span of the prose to a span of the source."""
        end = max(end, start + 1)
        return self.offsets[start], self.offsets[end - 1] + 1

    def is_contiguous(self, start: int, end: int) -> bool:
        """True if prose[start:end] sits unbroken in the source too."""
        return all(
            self.offsets[k + 1] == self.offsets[k] + 1 for k in range(start, end - 1)
        )


class Source:
    """The original file, for turning offsets into lines, columns and snippets."""

    def __init__(self, text: str, path: str = ""):
        self.text = text
        self.path = path
        self.line_starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line_col(self, offset: int) -> tuple[int, int]:
        """1-based line and column of a source offset."""
        line = bisect_right(self.line_starts, offset) - 1
        return line + 1, offset - self.line_starts[line] + 1

    def line_text(self, line: int) -> str:
        start = self.line_starts[line - 1]
        end = self.text.find("\n", start)
        return self.text[start:] if end == -1 else self.text[start:end]


PARAGRAPH = re.compile(r"(?:[^\n]|\n(?![ \t]*\n))+")


def paragraphs(text: str):
    """Yield (offset, paragraph) for each run of text between blank lines."""
    for m in PARAGRAPH.finditer(text):
        if m.group().strip():
            yield m.start(), m.group()


class LatexToProse:
    """One-pass LaTeX reader that writes into a Prose object."""

    def __init__(self, src: str):
        self.src = src
        self.n = len(src)
        self.end = self.n
        self.out = Prose()
        self.notes: list[Prose] = []
        self.bold_depth = 0

    # ── entry point ──
    def convert(self) -> Prose:
        begin = re.search(r"\\begin\s*\{document\}", self.src)
        finish = re.search(r"\\end\s*\{document\}", self.src)
        start = begin.end() if begin else 0
        self.end = finish.start() if finish else self.n
        self.walk(start, closing=False)
        result = self.out
        for note in self.notes:
            if note.chars:
                result.put(BREAK, note.offsets[0])
                result.extend(note)
        return result

    # ── output ──
    def emit(self, text: str, offset: int) -> None:
        self.out.put(text, offset, self.bold_depth > 0)

    # ── main loop ──
    def walk(self, i: int, closing: bool) -> int:
        """Read from i; if `closing`, stop after the matching '}'. Return the new index."""
        src = self.src
        while i < self.end:
            c = src[i]
            if c == "}":
                i += 1
                if closing:
                    return i
            elif c == "{":
                i = self.walk(i + 1, closing=True)
            elif c == "%":
                i = self.skip_comment(i)
            elif c == "\\":
                i = self.command(i)
            elif c == "$":
                i = self.skip_dollar_maths(i)
            elif c in "~&":
                self.emit(" ", i)
                i += 1
            elif c in "#^_":
                i += 1
            else:
                self.emit(c, i)
                i += 1
        return i

    # ── commands ──
    def command(self, i: int) -> int:
        src = self.src
        nxt = src[i + 1] if i + 1 < self.n else ""
        if nxt == "\\":  # \\ line break, maybe \\* or \\[2pt]
            j = i + 2
            if src.startswith("*", j):
                j += 1
            self.emit(BREAK, i)
            return self.skip_optional(j)
        if nxt.isascii() and (nxt.isalpha() or nxt == "@"):
            j = i + 1
            while j < self.n and src[j].isascii() and (src[j].isalpha() or src[j] == "@"):
                j += 1
            name = src[i + 1 : j]
            if src.startswith("*", j):
                j += 1
            return self.dispatch(name, i, self.skip_space_after_word(j))
        if nxt and nxt in "&%$#_{}":
            self.emit(nxt, i + 1)
            return i + 2
        if nxt and nxt in " \t\n,;:!>":  # explicit and thin spaces
            self.emit(" ", i)
            return i + 2
        if nxt == "(":
            end = src.find("\\)", i + 2)
            self.emit("0", i)
            return self.end if end == -1 else end + 2
        if nxt == "[":
            end = src.find("\\]", i + 2)
            self.emit(BREAK, i)
            return self.end if end == -1 else end + 2
        # Accents (\'e, \"{o}), \- discretionary hyphens, \/ and the like:
        # drop the command and let the letter that follows through.
        return i + 2

    def dispatch(self, name: str, i: int, j: int) -> int:
        src = self.src
        if name in ("begin", "end"):
            return self.environment(name, i, j)
        if name in NOTES:
            j = self.skip_optional(self.skip_ws(j))
            if j < self.n and src[j] == "{":
                saved, self.out = self.out, Prose()
                j = self.walk(j + 1, closing=True)
                self.notes.append(self.out)
                self.out = saved
            return j
        if name in DROP_ARGS:
            for _ in range(DROP_ARGS[name]):
                j = self.skip_argument(j)
            return j
        if name in QUOTES:
            j = self.skip_ws(j)
            if j < self.n and src[j] == "{":
                left, right = QUOTES[name]
                self.emit(left, j)
                j = self.walk(j + 1, closing=True)
                self.emit(right, j - 1)
            return j
        if name in BOLD:
            if j < self.n and src[j] == "{":
                self.bold_depth += 1
                j = self.walk(j + 1, closing=True)
                self.bold_depth -= 1
            return j
        if name in HEADINGS:
            j = self.skip_optional(j)
            self.emit(BREAK, i)
            if j < self.n and src[j] == "{":
                start = len(self.out.chars)
                j = self.walk(j + 1, closing=True)
                if name in TITLES:
                    self.out.titles.append((start, len(self.out.chars)))
                self.emit(BREAK, j - 1)
            return j
        if name in BREAKS:
            self.emit(BREAK, i)
            return self.skip_optional(j) if name == "item" else j
        if name in MACROS:
            self.emit(MACROS[name], i)
        return j

    def environment(self, name: str, i: int, j: int) -> int:
        src = self.src
        j = self.skip_ws(j)
        if j >= self.n or src[j] != "{":
            return j
        close = src.find("}", j)
        if close == -1:
            return self.end
        env = src[j + 1 : close].strip()
        j = close + 1
        self.emit(BREAK, i)
        if name == "end":
            return j
        if env in SKIP_ENVS:
            end = re.compile(r"\\end\s*\{" + re.escape(env) + r"\}").search(src, j)
            return self.end if end is None else end.end()
        j = self.skip_optional(j)
        for _ in range(ENV_ARGS.get(env, 0)):
            j = self.skip_argument(j)
        return j

    # ── skipping ──
    def skip_comment(self, i: int) -> int:
        """Skip a % comment, its newline and the next line's indent, as TeX does."""
        src = self.src
        j = src.find("\n", i)
        if j == -1:
            return self.end
        j += 1
        while j < self.n and src[j] in " \t":
            j += 1
        if j < self.n and src[j] == "\n":  # a blank line follows: keep the paragraph break
            self.emit("\n", j - 1)
        return j

    def skip_dollar_maths(self, i: int) -> int:
        src = self.src
        if src.startswith("$$", i):
            end = src.find("$$", i + 2)
            self.emit(BREAK, i)
            return self.end if end == -1 else end + 2
        j = i + 1
        while j < self.n:
            if src[j] == "\\":
                j += 2
                continue
            if src[j] == "$":
                self.emit("0", i)  # stands in for the formula, so no gap opens up
                return j + 1
            j += 1
        return self.end

    def skip_space_after_word(self, j: int) -> int:
        """TeX swallows spaces after a control word, and one newline unless a blank line follows."""
        src = self.src
        while j < self.n and src[j] in " \t":
            j += 1
        if j < self.n and src[j] == "\n":
            k = j + 1
            while k < self.n and src[k] in " \t":
                k += 1
            if k < self.n and src[k] != "\n":
                return k
        return j

    def skip_ws(self, j: int) -> int:
        while j < self.n and self.src[j] in " \t\n":
            j += 1
        return j

    def skip_optional(self, j: int) -> int:
        """Skip an [optional] argument that starts exactly at j."""
        src = self.src
        if j >= self.n or src[j] != "[":
            return j
        k = j + 1
        while k < self.n:
            if src[k] == "{":
                k = self.match_brace(k)
            elif src[k] == "\\":
                k += 2
            elif src[k] == "]":
                return k + 1
            else:
                k += 1
        return j

    def skip_argument(self, j: int) -> int:
        """Skip one argument, whatever its form: {group}, \\command or single token."""
        src = self.src
        j = self.skip_optional(self.skip_ws(j))
        j = self.skip_ws(j)
        if j >= self.n:
            return j
        if src[j] == "{":
            return self.match_brace(j)
        if src[j] == "\\":
            k = j + 1
            while k < self.n and src[k].isascii() and src[k].isalpha():
                k += 1
            return max(k, j + 2)
        return j + 1

    def match_brace(self, j: int) -> int:
        """Index just after the '}' matching the '{' at j."""
        src = self.src
        depth = 0
        k = j
        while k < self.n:
            c = src[k]
            if c == "\\":
                k += 2
                continue
            if c == "%":
                nl = src.find("\n", k)
                k = self.n if nl == -1 else nl
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return k + 1
            k += 1
        return self.n


def extract(src: str) -> Prose:
    """Extract the prose from LaTeX source."""
    return LatexToProse(src).convert()
