"""Read LaTeX source into `Prose`, in one pass.

* Only the body is read (between \\begin{document} and \\end{document}).
* Comments, maths and verbatim-like environments are dropped.
* Commands vanish, but the text in their arguments stays, so
  "the \\textbf{the}" still reads as "the the". Commands whose arguments are
  not prose (\\label, \\vspace, ...) lose their arguments too.
* Footnotes are lifted out and checked as paragraphs of their own, so the
  sentence they interrupt stays whole.
* Line breaks (\\\\), headings, environments and list items become paragraph
  breaks, which stops checks joining lyric lines or a heading to its text.
* \\say{..} and \\bsq{..} become curly double and single quotes.
* Text set in \\textbf (and similar) is marked bold: the spelling stage
  skips bold names of bands, people and places.

Which command gets which treatment is in the tables of commands.py.
"""

import re

from .commands import (
    BOLD,
    BREAKS,
    DROP_ARGS,
    ENV_ARGS,
    HEADINGS,
    MACROS,
    NOTES,
    QUOTES,
    SKIP_ENVS,
    SPACES,
    TITLES,
)
from .prose import BREAK, Prose


def extract(src: str) -> Prose:
    """The prose of a LaTeX document, footnotes last."""
    return LatexToProse(src).convert()


#: After \noindent: spaces and spacing commands, then a lower-case letter.
_RESUMES = re.compile(
    r"(?:\s|\\(?:hspace\*?\{[^}]*\}|quad|qquad|enspace|enskip|thinspace|,))*[a-z]"
)

#: Characters with no special meaning to the reader, copied as they are.
_PLAIN = re.compile(r"[^{}%\\$~&#^_]+")


def _is_letter(c: str) -> bool:
    """A letter of a command name: ASCII letters and @."""
    return c.isascii() and (c.isalpha() or c == "@")


class LatexToProse:
    """One-pass LaTeX reader. Every method takes the index to read from and
    returns the index just after what it consumed."""

    def __init__(self, src: str):
        self.src = src
        self.n = len(src)
        self.end = self.n            # where \end{document} starts
        self.out = Prose()
        self.notes: list[Prose] = []
        self.bold_depth = 0

    def convert(self) -> Prose:
        begin = re.search(r"\\begin\s*\{document\}", self.src)
        finish = re.search(r"\\end\s*\{document\}", self.src)
        self.end = finish.start() if finish else self.n
        self.walk(begin.end() if begin else 0, closing=False)
        for note in self.notes:
            if note.chars:
                self.out.put(BREAK, note.offsets[0])
                self.out.extend(note)
        return self.out

    def emit(self, text: str, offset: int) -> None:
        self.out.put(text, offset, self.bold_depth > 0)

    # ── the main loop ──

    def walk(self, i: int, closing: bool) -> int:
        """Read from i; if `closing`, stop after the matching '}'."""
        src = self.src
        while i < self.end:
            match src[i]:
                case "}":
                    i += 1
                    if closing:
                        return i
                case "{":
                    i = self.walk(i + 1, closing=True)
                case "%":
                    i = self.skip_comment(i)
                case "\\":
                    i = self.command(i)
                case "$":
                    i = self.skip_dollar_maths(i)
                case "~" | "&":
                    self.emit(" ", i)
                    i += 1
                case "#" | "^" | "_":
                    i += 1
                case _:  # plain text: copy the run up to the next special character
                    run = _PLAIN.match(src, i, self.end)
                    self.out.put_run(run.group(), i, self.bold_depth > 0)
                    i = run.end()
        return i

    # ── commands ──

    def command(self, i: int) -> int:
        """A backslash at i: a control word, a control symbol or \\\\."""
        src = self.src
        nxt = src[i + 1] if i + 1 < self.n else ""
        if nxt == "\\":  # \\ line break, maybe \\* or \\[2pt]
            self.emit(BREAK, i)
            return self.skip_optional(i + 3 if src.startswith("*", i + 2) else i + 2)
        if _is_letter(nxt):
            j = i + 1
            while j < self.n and _is_letter(src[j]):
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
        if nxt in ("(", "["):  # \( inline maths \) and \[ display maths \]
            end = src.find("\\)" if nxt == "(" else "\\]", i + 2)
            self.emit("0" if nxt == "(" else BREAK, i)
            return self.end if end == -1 else end + 2
        # Accents (\'e, \"{o}), \- discretionary hyphens, \/ and the like:
        # drop the command and let the letter that follows through.
        return i + 2

    def dispatch(self, name: str, i: int, j: int) -> int:
        """The control word `name` at i, its arguments starting at j."""
        if name in ("begin", "end"):
            return self.environment(name, i, j)
        if name == "noindent":
            return self._noindent(i, j)
        for table, handler in self._HANDLERS:
            if name in table:
                return handler(self, name, i, j)
        return j

    def _noindent(self, i: int, j: int) -> int:
        """`\\noindent` before a lower-case word: the paragraph before goes on
        (text resumed after a picture or a quotation), so the break between
        is a space, not a new sentence."""
        if not (_RESUMES.match(self.src, j) and self.out.text.strip()):
            return j
        kept = len(self.out.text.rstrip())
        if any(end == kept for _, end in self.out.titles):
            return j   # a heading is never joined to the text after it
        self.out.drop_trailing_space()
        self.emit(" ", i)
        return j

    def _note(self, name: str, i: int, j: int) -> int:
        """A footnote: read into a Prose of its own, added at the end."""
        j = self.skip_optional(self.skip_ws(j))
        if self._opens(j):
            saved, self.out = self.out, Prose()
            j = self.walk(j + 1, closing=True)
            self.notes.append(self.out)
            self.out = saved
        return j

    def _drop(self, name: str, i: int, j: int) -> int:
        for _ in range(DROP_ARGS[name]):
            j = self.skip_argument(j)
        return j

    def _space(self, name: str, i: int, j: int) -> int:
        """Horizontal space: its amount is dropped, the words stay apart.

        No space is added after one already there: "sight \\hspace{17pt}and"
        is one space, not a double space (the added one would sit next to
        the real one in the source).
        """
        for _ in range(SPACES[name]):
            j = self.skip_argument(j)
        if not (self.out.chars and self.out.chars[-1] in " \t"):
            self.emit(" ", i)
        return j

    def _quote(self, name: str, i: int, j: int) -> int:
        j = self.skip_ws(j)
        if self._opens(j):
            left, right = QUOTES[name]
            self.emit(left, j)
            j = self.walk(j + 1, closing=True)
            self.emit(right, j - 1)
        return j

    def _bold(self, name: str, i: int, j: int) -> int:
        if self._opens(j):
            self.bold_depth += 1
            j = self.walk(j + 1, closing=True)
            self.bold_depth -= 1
        return j

    def _heading(self, name: str, i: int, j: int) -> int:
        """A heading's text, set off by breaks; titles are recorded."""
        j = self.skip_optional(j)
        self.emit(BREAK, i)
        if self._opens(j):
            start = len(self.out.chars)
            j = self.walk(j + 1, closing=True)
            if name in TITLES:
                self.out.titles.append((start, len(self.out.chars)))
            if name == "part":
                self.out.parts.append((start, len(self.out.chars)))
            self.emit(BREAK, j - 1)
        return j

    def _break(self, name: str, i: int, j: int) -> int:
        self.emit(BREAK, i)
        return self.skip_optional(j) if name == "item" else j

    def _macro(self, name: str, i: int, j: int) -> int:
        self.emit(MACROS[name], i)
        return j

    # Checked in this order; a command in none of them simply vanishes.
    _HANDLERS = ((NOTES, _note), (DROP_ARGS, _drop), (SPACES, _space), (QUOTES, _quote),
                 (BOLD, _bold), (HEADINGS, _heading), (BREAKS, _break), (MACROS, _macro))

    def environment(self, name: str, i: int, j: int) -> int:
        """\\begin{env} or \\end{env}: a break; skipped environments vanish whole."""
        src = self.src
        j = self.skip_ws(j)
        if not self._opens(j):
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

    def _opens(self, j: int) -> bool:
        """True if a {group} starts at j."""
        return j < self.n and self.src[j] == "{"

    def skip_comment(self, i: int) -> int:
        """Skip a % comment, its newline and the next line's indent, as TeX does."""
        j = self.src.find("\n", i)
        if j == -1:
            return self.end
        j = self._skip_blanks(j + 1)
        if j < self.n and self.src[j] == "\n":  # a blank line follows: keep the break
            self.emit("\n", j - 1)
        return j

    def skip_dollar_maths(self, i: int) -> int:
        """$...$ becomes "0", so no gap opens up; $$...$$ becomes a break."""
        src = self.src
        if src.startswith("$$", i):
            end = src.find("$$", i + 2)
            self.emit(BREAK, i)
            return self.end if end == -1 else end + 2
        j = i + 1
        while j < self.n:
            if src[j] == "\\":
                j += 2
            elif src[j] == "$":
                self.emit("0", i)
                return j + 1
            else:
                j += 1
        return self.end

    def _skip_blanks(self, j: int) -> int:
        """Skip spaces and tabs (not newlines)."""
        while j < self.n and self.src[j] in " \t":
            j += 1
        return j

    def skip_space_after_word(self, j: int) -> int:
        """TeX swallows spaces after a control word, and one newline unless a
        blank line follows."""
        j = self._skip_blanks(j)
        if j < self.n and self.src[j] == "\n":
            k = self._skip_blanks(j + 1)
            if k < self.n and self.src[k] != "\n":
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
        j = self.skip_ws(self.skip_optional(self.skip_ws(j)))
        if j >= self.n:
            return j
        if self.src[j] == "{":
            return self.match_brace(j)
        if self.src[j] == "\\":
            k = j + 1
            while k < self.n and self.src[k].isascii() and self.src[k].isalpha():
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
