"""Stage 6: layout, on the typeset lines of the PDF beside the .tex.

These depend on where TeX broke the lines, so they read the PDF
(`document.pdf` beside `document.tex`; see pdfwords.py) and match each line
back to the source, so every finding still opens at its line:column.

* **Runts:** a paragraph whose last line is a single word.
* **Lone "I"s at the edges:** a line that starts or ends with the word "I",
  PARAGRAPH_I or more times in one paragraph, or PAGE_I or more on a page.
* **Stacks:** the same word starting, or ending, two lines running; and any
  word directly above the same word (overlapping by 80% of its width).

All thresholds are constants here. A PDF older than the .tex is used anyway
and said to be out of date; findings it cannot match to the source (the
text has changed since) are counted, not shown.
"""

from __future__ import annotations

import difflib
import re
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass

from .. import pdfwords
from ..findings import Finding, Skipped
from ..pdfwords import Line, Word, lines_of

NAME = "layout"
TITLE = "Layout"
BLURB = "line breaks in the typeset PDF"

PARAGRAPH_I = 2
PAGE_I = 3
#: How far short of the right margin, in points, a line must end to close a paragraph.
SHORT_OF_MARGIN = 15.0
#: Overlap, as a share of the narrower word, for "directly above".
ABOVE_OVERLAP = 0.8

TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")

__all__ = ["Skipped", "find", "run"]


@dataclass
class Hit:
    kind: str
    page: int         # 0-based PDF page
    line: int         # 1-based body line on that page
    word: Word        # where to point
    message: str


def _key(word: Word) -> str:
    tokens = TOKEN.findall(word.text)
    return tokens[0].replace("’", "'").lower() if len(tokens) == 1 else ""


def _body(words: list[Word]) -> list[Line]:
    """A page's lines, without page numbers."""
    return [ln for ln in lines_of(words) if not (len(ln) == 1 and ln[0].text.strip("()[]").isdigit())]


def _margins(lines: list[Line]) -> tuple[float, float]:
    """Where most lines start and end. Not min and max: a stray mark at the
    page edge (some PDFs have one on every page) would move them."""
    def mode(values: list[float]) -> float:
        return Counter(round(v) for v in values).most_common(1)[0][0] if values else 0.0
    long = [ln for ln in lines if len(ln) >= 4] or lines
    return mode([ln[0].x0 for ln in long]) - 0.5, mode([ln[-1].x1 for ln in long]) + 0.5


def _overlap(a: Word, b: Word) -> float:
    width = min(a.x1 - a.x0, b.x1 - b.x0) or 1.0
    return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0)) / width


def _lone_i(line: Line, left: float, right: float) -> int:
    """How many edges of this line hold a lone I (0, 1 or 2)."""
    count = 0
    if _key(line[0]) == "i" and line[0].x0 <= left + 2:
        count += 1
    if len(line) > 1 and _key(line[-1]) == "i" and line[-1].x1 >= right - 2:
        count += 1
    return count


def find(pages: list[list[Word]], titles: set[int] | frozenset = frozenset()) -> list[Hit]:
    """Every layout problem in the typeset pages, in page order.

    `titles` holds the id() of words that belong to section and chapter
    titles. A line made mostly of them is a title: it is not checked or
    compared with its neighbours, and it ends the paragraph before it.
    """
    hits: list[Hit] = []
    previous: Line | None = None  # carries over a page break, for runts
    previous_full = False
    for number, words in enumerate(pages):
        lines = _body(words)
        if not lines:
            continue
        is_title = [sum(id(w) in titles for w in ln) * 2 > len(ln) for ln in lines]
        left, right = _margins([ln for ln, t in zip(lines, is_title) if not t] or lines)
        full = [ln[-1].x1 >= right - SHORT_OF_MARGIN and len(ln) > 1 and not t
                for ln, t in zip(lines, is_title)]
        page_i: list[int] = []
        para_i: list[int] = []
        for index, ln in enumerate(lines):
            at = index + 1
            prev_full = full[index - 1] if index else previous_full
            prev_line = lines[index - 1] if index else previous
            if is_title[index]:
                para_i = []  # a title ends the paragraph before it
                continue
            # Runts: a paragraph's last line, one word, after a full line.
            if (not full[index] and len(ln) == 1 and prev_line is not None and prev_full
                    and ln[0].text[-1] in _ENDS_PARAGRAPH):
                hits.append(Hit("runt", number, at, ln[0],
                                f"one word on the last line of a paragraph: “{ln[0].text}”"))
            # Lone I at the edges, counted per paragraph and per page.
            if (edges := _lone_i(ln, left, right)):
                para_i += [at] * edges
                page_i += [at] * edges
            if not full[index]:  # the paragraph ends here
                if len(para_i) >= PARAGRAPH_I:
                    hits.append(Hit("lone-i", number, para_i[0], _first_i(lines[para_i[0] - 1]),
                                    f"{len(para_i)} lone “I”s at line edges in this paragraph "
                                    f"({_line_list(para_i)})"))
                    page_i = [n for n in page_i if n not in para_i]
                para_i = []
            # Stacks, against the line above on this page.
            if index and not is_title[index - 1]:
                hits += _stacks(lines[index - 1], ln, number, at, full[index - 1], full[index], left)
        if len(page_i) >= PAGE_I:
            hits.append(Hit("lone-i", number, page_i[0], _first_i(lines[page_i[0] - 1]),
                            f"{len(page_i)} lone “I”s at line edges on this page "
                            f"({_line_list(page_i)})"))
        previous, previous_full = (None, False) if is_title[-1] else (lines[-1], full[-1])
    return hits


def _line_list(numbers: list[int]) -> str:
    distinct = sorted(set(numbers))
    return ("line " if len(distinct) == 1 else "lines ") + ", ".join(map(str, distinct))


def _shown(word: Word) -> str:
    """The word as written, without its punctuation: “I”, not “i”."""
    tokens = TOKEN.findall(word.text)
    return tokens[0] if tokens else word.text


def _first_i(line: Line) -> Word:
    return line[0] if _key(line[0]) == "i" else line[-1]


def _stacks(upper: Line, lower: Line, page: int, at: int, upper_full: bool,
            lower_full: bool, left: float) -> list[Hit]:
    hits = []
    starts = len(upper) > 1 and len(lower) > 1 and upper[0].x0 <= left + 2 and lower[0].x0 <= left + 2
    if starts and _key(upper[0]) and _key(upper[0]) == _key(lower[0]):
        hits.append(Hit("stack", page, at, lower[0], f"“{_shown(lower[0])}” starts two lines running"))
    ends = upper_full and lower_full
    if ends and _key(upper[-1]) and _key(upper[-1]) == _key(lower[-1]):
        hits.append(Hit("stack", page, at, lower[-1], f"“{_shown(lower[-1])}” ends two lines running"))
    for i, word in enumerate(lower):
        key = _key(word)
        if not key or (i == 0 and starts) or (i == len(lower) - 1 and ends):
            continue
        for j, above in enumerate(upper):
            if (j == 0 and i == 0) or (j == len(upper) - 1 and i == len(lower) - 1):
                continue
            if _key(above) == key and _overlap(above, word) >= ABOVE_OVERLAP:
                hits.append(Hit("stack", page, at, word, f"“{_shown(word)}” directly above “{_shown(above)}”"))
                break
    return hits


# ── repairing glued lines ───────────────────────────────────────────────────

def _segment(letters: str, vocab: set[str]) -> list[str]:
    """`letters` cut into words of `vocab`, as few as possible. A piece not in
    the vocabulary (the tail of a word hyphenated on the line above) is
    allowed but costs more the longer it is, so real words always win."""
    lower = letters.replace("’", "'").lower()
    INF = float("inf")
    cost = [0.0] + [INF] * len(lower)
    back = [0] * (len(lower) + 1)
    for end in range(1, len(lower) + 1):
        for start in range(max(0, end - 30), end):
            if cost[start] == INF:
                continue
            size = end - start
            step = 1 if lower[start:end] in vocab else (2 + size if size <= 15 else INF)
            if cost[start] + step < cost[end]:
                cost[end], back[end] = cost[start] + step, start
    pieces, end = [], len(lower)
    while end:
        pieces.append(letters[back[end]:end])
        end = back[end]
    return pieces[::-1]


_OPENING = set("“‘([")
#: A paragraph's last word ends with one of these; a heading's does not.
_ENDS_PARAGRAPH = set(".!?:;)”’—…'\"")


def _split_glued(text: str, vocab: set[str]) -> list[str]:
    """The words of a run-together "word", or [text] if it is one word."""
    words: list[str] = []
    prefix = ""      # opening marks waiting for the next word
    join = False     # a hyphen: the next piece continues the last word
    for part in re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)*|\d+|[^\w]", text):
        if TOKEN.fullmatch(part):
            pieces = [part] if part.replace("’", "'").lower() in vocab else _segment(part, vocab)
            if join and words:
                words[-1] += pieces[0]
                pieces = pieces[1:]
            if pieces:
                pieces[0] = prefix + pieces[0]
                prefix = ""
            words += pieces
            join = False
        elif part in _OPENING:
            prefix += part
        elif part == "-" and words:
            words[-1] += part
            join = True
        elif words:
            words[-1] += part
        else:
            prefix += part
    if prefix:
        words.append(prefix)
    return words if len(words) > 1 else [text]


def unglue(pages: list[list[Word]], vocab: set[str]) -> list[list[Word]]:
    """Split run-together words using the book's own vocabulary, sharing out
    each one's width by letter count (its letters' boxes touch, so there is
    no better guide)."""
    out = []
    for words in pages:
        fixed: list[Word] = []
        for word in words:
            parts = _split_glued(word.text, vocab) if len(word.text) >= 12 else [word.text]
            if len(parts) == 1:
                fixed.append(word)
                continue
            total = sum(len(p) for p in parts)
            per = (word.x1 - word.x0) / total
            x = word.x0
            for n, part in enumerate(parts):
                end = word.x1 if n == len(parts) - 1 else x + per * len(part)
                fixed.append(Word(part, round(x, 1), round(end, 1), word.y))
                x = end
        out.append(fixed)
    return out


# ── matching the typeset words back to the prose ────────────────────────────

def _pdf_tokens(pages: list[list[Word]]) -> list[tuple[str, Word]]:
    """(token, word) for every word, a line-end hyphen joined to the next line."""
    out: list[tuple[str, Word]] = []
    carry: tuple[str, Word] | None = None
    for words in pages:
        for ln in _body(words):
            for k, word in enumerate(ln):
                tokens = [t.replace("’", "'").lower() for t in TOKEN.findall(word.text)]
                if carry and k == 0 and tokens:
                    tokens[0] = carry[0] + tokens[0]
                    out.append((tokens[0], carry[1]))
                    out.append((tokens[0], word))  # either half points at the same token
                    tokens = tokens[1:]
                    carry = None
                elif carry:
                    out.append(carry)
                    carry = None
                hyphen = k == len(ln) - 1 and word.text.endswith("-") and tokens
                for t in tokens[:-1] if hyphen else tokens:
                    out.append((t, word))
                if hyphen:
                    carry = (tokens[-1], word)
    if carry:
        out.append(carry)
    return out


def _anchors(pdf: list[str], prose: list[str], size: int = 4) -> list[tuple[int, int]]:
    """Runs of `size` tokens found exactly once in each text, kept only where
    they come in the same order in both (a longest increasing subsequence)."""
    def unique(tokens: list[str]) -> dict[tuple[str, ...], int]:
        seen: dict[tuple[str, ...], int] = {}
        for k in range(len(tokens) - size + 1):
            gram = tuple(tokens[k:k + size])
            seen[gram] = -1 if gram in seen else k
        return {g: k for g, k in seen.items() if k >= 0}

    theirs = unique(prose)
    pairs = sorted((i, theirs[g]) for g, i in unique(pdf).items() if g in theirs)
    # Longest increasing run of prose positions, in pdf order.
    tails: list[int] = []        # prose position ending a run of each length
    tail_at: list[int] = []      # index into pairs of that end
    parent = [-1] * len(pairs)
    for n, (_, j) in enumerate(pairs):
        k = bisect_left(tails, j)
        if k == len(tails):
            tails.append(j)
            tail_at.append(n)
        else:
            tails[k], tail_at[k] = j, n
        parent[n] = tail_at[k - 1] if k else -1
    chain, n = [], tail_at[-1] if tail_at else -1
    while n >= 0:
        chain.append(pairs[n])
        n = parent[n]
    return chain[::-1]


def _align(pdf: list[str], prose: list[str], size: int = 4, gap_limit: int = 4000) -> dict[int, int]:
    """Map pdf token indices to prose token indices.

    Text that is only in the PDF (contents, running heads, footnotes, which
    the prose holds at the end) is left unmapped. Anchors are runs found once
    in both; between two anchors the tokens are matched by difflib.
    """
    found: dict[int, int] = {}
    previous = (0, 0)
    for i, j in _anchors(pdf, prose, size) + [(len(pdf), len(prose))]:
        a0, b0 = previous
        if i >= a0 and j >= b0 and max(i - a0, j - b0) <= gap_limit:
            matcher = difflib.SequenceMatcher(None, pdf[a0:i], prose[b0:j], autojunk=False)
            for block in matcher.get_matching_blocks():
                for k in range(block.size):
                    found[a0 + block.a + k] = b0 + block.b + k
        for k in range(size if i < len(pdf) else 0):
            found[i + k] = j + k
        previous = (i + size, j + size)
    return found


def _title_words(pdf: list[tuple[str, Word]], mapping: dict[int, int],
                 spans: list[tuple[int, int]], titles: list[tuple[int, int]]) -> set[int]:
    """id() of the typeset words that match title text in the prose."""
    if not titles:
        return set()
    starts = sorted(titles)
    found = set()
    for index, (_, word) in enumerate(pdf):
        if index in mapping:
            at = spans[mapping[index]][0]
            k = bisect_left(starts, (at + 1,)) - 1
            if k >= 0 and starts[k][0] <= at < starts[k][1]:
                found.add(id(word))
    return found


def run(prose, settings) -> list[Finding]:
    if settings.pdf is None:
        raise Skipped("no PDF beside the .tex (typeset it first)")
    try:
        pages = pdfwords.read(settings.pdf)
    except pdfwords.Unreadable as err:
        raise Skipped(str(err)) from err
    text = prose.text  # built afresh on each access: read it once
    spans = [m.span() for m in TOKEN.finditer(text)]
    texts = [text[a:b].replace("’", "'").lower() for a, b in spans]
    pages = unglue(pages, set(texts))

    pdf = _pdf_tokens(pages)
    mapping = _align([t for t, _ in pdf], texts)
    hits = find(pages, _title_words(pdf, mapping, spans, prose.titles))
    first_index: dict[int, int] = {}
    for index, (_, word) in enumerate(pdf):
        if index in mapping:
            first_index.setdefault(id(word), mapping[index])

    findings, unmatched = [], 0
    for hit in hits:
        at = first_index.get(id(hit.word))
        if at is None:
            unmatched += 1
            continue
        start, end = spans[at]
        findings.append(Finding(NAME, start, end, hit.message,
                                note=f"PDF page {hit.page + 1}, line {hit.line}"))
    settings.stats[NAME] = {"unmatched": unmatched, "stale": settings.pdf_stale}
    return findings
