"""The layout problems on typeset pages: runts, lone "I"s and stacks.

Each page is measured once (`_Page`), then each kind of problem has its
own short pass over its lines.
"""

from collections import Counter
from dataclasses import dataclass

from ...pdfwords import Line, Word
from .words import body, key, shown

PARAGRAPH_I = 2   # lone "I"s at line edges in one paragraph that are too many
PAGE_I = 3        # ... and on one page
#: How far short of the right margin, in points, a line must end to close a paragraph.
SHORT_OF_MARGIN = 15.0
#: "Directly above": the two centres at most this share of the word's width
#: apart. Askew is fine (asked for 23 November 2026): only a word squarely on
#: top of itself looks wrong. On the test book: 50% gave 447, 10% gives 148.
ABOVE_SHIFT = 0.10
#: A stack of three or more: each word's centre at most this share of the
#: word's width from the one above, so 1.0 is "the two overlap". Askew counts
#: here (asked for 24 November 2026): three of the same word down a page
#: catch the eye even at an angle. On the test book: 0.5 gave 11, 1.0 gives 28.
STACK_SHIFT = 1.0
#: How many lines running make a stack of the same word.
STACK_LINES = 3
#: How near the margin, in points, a word must be to count as at the edge.
EDGE = 2.0
#: A paragraph's last word ends with one of these; a heading's does not.
_ENDS_PARAGRAPH = set(".!?:;)”’—…'\"")


@dataclass
class Hit:
    kind: str         # runt, lone-i, starts, ends, stack, above (see groups.LAYOUT_GROUPS)
    page: int         # 0-based PDF page
    line: int         # 1-based body line on that page
    word: Word        # where to point
    message: str


@dataclass
class _Page:
    """One page's body lines, measured."""

    number: int
    lines: list[Line]
    title: list[bool]   # per line: a section or chapter title
    full: list[bool]    # per line: runs to the right margin (the paragraph goes on)
    left: float
    right: float
    keys: list[list[str]]   # per line, each word's key (worked out once: it is a regex)


def find(pages: list[list[Word]], titles: set[int] | frozenset = frozenset()) -> list[Hit]:
    """Every layout problem in the typeset pages, page by page (each page's
    runts, then lone "I"s, then stacks of three, then pairs).

    `titles` holds the id() of words that belong to section and chapter
    titles. A line made mostly of them is a title: it is not checked or
    compared with its neighbours, and it ends the paragraph before it.
    """
    hits: list[Hit] = []
    carried_full = False  # the last line of the page before ran full (for runts)
    for number, words in enumerate(pages):
        if not (lines := body(words)):
            continue
        page = _measure(number, lines, titles)
        stacks, stacked = _tall_stacks(page)
        pairs = [h for h in _stacks_on(page) if not (h.kind == "above" and id(h.word) in stacked)]
        hits += _runts(page, carried_full) + _lone_is(page) + stacks + pairs
        carried_full = page.full[-1]
    return hits


def _measure(number: int, lines: list[Line], titles: set[int] | frozenset) -> _Page:
    title = [sum(id(w) in titles for w in ln) * 2 > len(ln) for ln in lines]
    text_lines = [ln for ln, t in zip(lines, title, strict=True) if not t]
    left, right = _margins(text_lines or lines)
    full = [len(ln) > 1 and ln[-1].x1 >= right - SHORT_OF_MARGIN and not t
            for ln, t in zip(lines, title, strict=True)]
    keys = [[key(w) for w in ln] for ln in lines]
    return _Page(number, lines, title, full, left, right, keys)


def _margins(lines: list[Line]) -> tuple[float, float]:
    """Where most lines start and end. Not min and max: a stray mark at the
    page edge (some PDFs have one on every page) would move them."""
    def mode(values: list[float]) -> float:
        return Counter(round(v) for v in values).most_common(1)[0][0] if values else 0.0
    long = [ln for ln in lines if len(ln) >= 4] or lines
    return mode([ln[0].x0 for ln in long]) - 0.5, mode([ln[-1].x1 for ln in long]) + 0.5


# ── runts ──

def _runts(page: _Page, carried_full: bool) -> list[Hit]:
    """A paragraph's last line holding one word, after a full line."""
    hits = []
    for index, ln in enumerate(page.lines):
        before_full = page.full[index - 1] if index else carried_full
        if page.title[index] or len(ln) != 1 or not before_full:
            continue
        if ln[0].text[-1] in _ENDS_PARAGRAPH:
            hits.append(Hit("runt", page.number, index + 1, ln[0],
                            f"one word on the last line of a paragraph: “{ln[0].text}”"))
    return hits


# ── lone "I"s at the edges ──

def _lone_is(page: _Page) -> list[Hit]:
    """Lone "I"s at line edges: PARAGRAPH_I in a paragraph, or PAGE_I on a
    page not already counted in a paragraph."""
    hits = []
    on_page: list[int] = []        # line numbers, once per lone I
    in_paragraph: list[int] = []
    for index, ln in enumerate(page.lines):
        if page.title[index]:
            in_paragraph = []  # a title ends the paragraph before it
            continue
        edges = _edge_is(ln, page.left, page.right)
        in_paragraph += [index + 1] * edges
        on_page += [index + 1] * edges
        if page.full[index]:
            continue
        if len(in_paragraph) >= PARAGRAPH_I:  # the paragraph ends here
            hits.append(_lone_i_hit(page, in_paragraph, "in this paragraph"))
            on_page = [n for n in on_page if n not in in_paragraph]
        in_paragraph = []
    if len(on_page) >= PAGE_I:
        hits.append(_lone_i_hit(page, on_page, "on this page"))
    return hits


def _edge_is(line: Line, left: float, right: float) -> int:
    """How many edges of this line hold a lone I (0, 1 or 2)."""
    starts = key(line[0]) == "i" and line[0].x0 <= left + EDGE
    ends = len(line) > 1 and key(line[-1]) == "i" and line[-1].x1 >= right - EDGE
    return starts + ends


def _lone_i_hit(page: _Page, numbers: list[int], where: str) -> Hit:
    first = page.lines[numbers[0] - 1]
    word = first[0] if key(first[0]) == "i" else first[-1]
    distinct = sorted(set(numbers))
    lines = ("line " if len(distinct) == 1 else "lines ") + ", ".join(map(str, distinct))
    return Hit("lone-i", page.number, numbers[0], word,
               f"{len(numbers)} lone “I”s at line edges {where} ({lines})")


# ── stacks ──

def _stacks_on(page: _Page) -> list[Hit]:
    """Each line against the one above it, titles left out."""
    hits = []
    for index in range(1, len(page.lines)):
        if not (page.title[index] or page.title[index - 1]):
            hits += _stacks(page, index)
    return hits


def _stacks(page: _Page, index: int) -> list[Hit]:
    """Line `index` against the line above: the same word starting or ending
    both, or squarely above itself."""
    upper, lower, at = page.lines[index - 1], page.lines[index], index + 1
    up_keys, low_keys = page.keys[index - 1], page.keys[index]
    hits = []
    starts = (len(upper) > 1 and len(lower) > 1
              and upper[0].x0 <= page.left + EDGE and lower[0].x0 <= page.left + EDGE)
    if starts and up_keys[0] and up_keys[0] == low_keys[0]:
        hits.append(Hit("starts", page.number, at, lower[0],
                        f"“{shown(lower[0])}” starts two lines running"))
    ends = page.full[index - 1] and page.full[index]
    if ends and up_keys[-1] and up_keys[-1] == low_keys[-1]:
        hits.append(Hit("ends", page.number, at, lower[-1],
                        f"“{shown(lower[-1])}” ends two lines running"))
    hits += [Hit("above", page.number, at, word, f"“{shown(word)}” directly above “{shown(up)}”")
             for word, up in _above(page, index, skip_first=starts, skip_last=ends)]
    return hits


def _above(page: _Page, index: int, skip_first: bool, skip_last: bool) -> list[tuple[Word, Word]]:
    """(word, the same word squarely above it) for each word of line `index`.
    Words already reported as starting or ending both lines are left out,
    and so are first-on-first and last-on-last (those are starts and ends)."""
    upper, lower = page.lines[index - 1], page.lines[index]
    where: dict[str, list[int]] = {}   # key → its places in the upper line
    for j, k in enumerate(page.keys[index - 1]):
        where.setdefault(k, []).append(j)
    pairs = []
    last, up_last = len(lower) - 1, len(upper) - 1
    for i, (word, k) in enumerate(zip(lower, page.keys[index], strict=True)):
        if not k or (i == 0 and skip_first) or (i == last and skip_last):
            continue
        for j in where.get(k, ()):
            if (i == j == 0) or (i == last and j == up_last):
                continue
            if _shift(upper[j], word) <= ABOVE_SHIFT:
                pairs.append((word, upper[j]))
                break
    return pairs


# ── stacks of three or more ──

def _tall_stacks(page: _Page) -> tuple[list[Hit], set[int]]:
    """The same word on STACK_LINES or more lines running, each within
    STACK_SHIFT of the one above; and the id() of every word in them, so a
    pair inside one is not reported again as "directly above".

    A stack made only of first words, or only of last words, is left to
    "starts" and "ends". Titles break a stack.
    """
    below: dict[int, list[Word]] = {}   # id() of a word → its stack so far, ending with it
    for index in range(1, len(page.lines)):
        if page.title[index] or page.title[index - 1]:
            continue
        upper = list(zip(page.lines[index - 1], page.keys[index - 1], strict=True))
        for word, k in zip(page.lines[index], page.keys[index], strict=True):
            near = [(_shift(up, word), up) for up, uk in upper if k and uk == k]
            near = [(shift, up) for shift, up in near if shift < STACK_SHIFT]
            if near:
                up = min(near, key=lambda pair: pair[0])[1]
                below[id(word)] = [*below.get(id(up), [up]), word]
    tops = {id(stack[-2]) for stack in below.values()}   # extended by a word below
    hits, stacked = [], set()
    for stack in below.values():
        if len(stack) < STACK_LINES or id(stack[-1]) in tops or _edges_only(page, stack):
            continue
        stacked |= {id(word) for word in stack}
        first = _line_of(page, stack[0])
        hits.append(Hit("stack", page.number, first + 1, stack[0],
                        f"“{shown(stack[0])}” on {len(stack)} lines running, one above another"))
    return hits, stacked


def _line_of(page: _Page, word: Word) -> int:
    return next(i for i, ln in enumerate(page.lines) if any(w is word for w in ln))


def _edges_only(page: _Page, stack: list[Word]) -> bool:
    """True if every word of the stack starts its line, or every one ends it."""
    lines = [page.lines[_line_of(page, word)] for word in stack]
    return (all(ln[0] is w for ln, w in zip(lines, stack, strict=True))
            or all(ln[-1] is w for ln, w in zip(lines, stack, strict=True)))


def _shift(a: Word, b: Word) -> float:
    """How far apart the two words' centres are, as a share of the wider one."""
    width = max(a.x1 - a.x0, b.x1 - b.x0) or 1.0
    return abs((a.x0 + a.x1) - (b.x0 + b.x1)) / 2 / width
