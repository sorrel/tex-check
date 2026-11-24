"""Match the typeset words back to the prose, so findings open at their
line:column in the .tex.

Anchors are runs of tokens found exactly once in both texts, kept where
they come in the same order (a longest increasing subsequence); between two
anchors difflib matches the rest. A simple cursor was not enough: the
contents pages repeat every chapter title before the chapters themselves.
"""

import difflib
from bisect import bisect_left

from ...pdfwords import Word
from .words import TOKEN, body, normal

ANCHOR = 4          # tokens in an anchor
GAP_LIMIT = 4000    # longest stretch between anchors worth handing to difflib


def pdf_tokens(pages: list[list[Word]]) -> list[tuple[str, Word]]:
    """(token, word) for every word, a line-end hyphen joined to the next line.
    Both halves of a hyphenated word point at the same token."""
    out: list[tuple[str, Word]] = []
    carry: tuple[str, Word] | None = None   # the first half of a hyphenated word
    for words in pages:
        for ln in body(words):
            for k, word in enumerate(ln):
                tokens = [normal(t) for t in TOKEN.findall(word.text)]
                if carry and k == 0 and tokens:
                    whole = carry[0] + tokens.pop(0)
                    out += [(whole, carry[1]), (whole, word)]
                elif carry:
                    out.append(carry)
                carry = None
                if k == len(ln) - 1 and word.text.endswith("-") and tokens:
                    carry = (tokens.pop(), word)
                out += [(t, word) for t in tokens]
    if carry:
        out.append(carry)
    return out


def align(pdf: list[str], prose: list[str]) -> dict[int, int]:
    """Map pdf token indices to prose token indices.

    Text that is only in the PDF (contents, running heads, footnotes, which
    the prose holds at the end) is left unmapped.
    """
    found: dict[int, int] = {}
    a0 = b0 = 0
    for i, j in [*anchors(pdf, prose), (len(pdf), len(prose))]:
        if i >= a0 and j >= b0 and max(i - a0, j - b0) <= GAP_LIMIT:
            matcher = difflib.SequenceMatcher(None, pdf[a0:i], prose[b0:j], autojunk=False)
            for block in matcher.get_matching_blocks():
                found.update((a0 + block.a + k, b0 + block.b + k) for k in range(block.size))
        if i < len(pdf):
            found.update((i + k, j + k) for k in range(ANCHOR))
        a0, b0 = i + ANCHOR, j + ANCHOR
    return found


def anchors(pdf: list[str], prose: list[str]) -> list[tuple[int, int]]:
    """(pdf index, prose index) of runs found once in each, in the same order
    in both."""
    theirs = _unique_runs(prose)
    pairs = sorted((i, theirs[g]) for g, i in _unique_runs(pdf).items() if g in theirs)
    return _increasing(pairs)


def _unique_runs(tokens: list[str]) -> dict[tuple[str, ...], int]:
    """Each run of ANCHOR tokens that appears once, with where it starts."""
    seen: dict[tuple[str, ...], int] = {}
    for k in range(len(tokens) - ANCHOR + 1):
        run = tuple(tokens[k:k + ANCHOR])
        seen[run] = -1 if run in seen else k
    return {run: k for run, k in seen.items() if k >= 0}


def _increasing(pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The longest run of `pairs` whose second values increase (patience
    sorting, O(n log n))."""
    tails: list[int] = []        # smallest second value ending a run of each length
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


def title_words(pdf: list[tuple[str, Word]], mapping: dict[int, int],
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
