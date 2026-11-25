"""Stage 6: layout, on the typeset lines of the PDF beside the .tex.

These depend on where TeX broke the lines, so they read the PDF
(`document.pdf` beside `document.tex`; see pdfwords.py) and match each line
back to the source, so every finding still opens at its line:column.

* **Headings at the foot:** a section or chapter title with fewer than
  three lines of text below it before the page turns.
* **Part pages on the left:** a \\part's own page (grey, in house style)
  on an even, left-hand page.
* **Runts:** a paragraph whose last line is a single word.
* **Lone "I"s at the edges:** a line that starts or ends with the word "I",
  too often in one paragraph or on one page.
* **Stacks:** the same word starting, or ending, two lines running; the
  same word on three lines running, one above another a little askew,
  or on four or more even at an angle;
  and any word squarely above the same word (askew is fine for two).

The modules: find.py (the checks and their thresholds), repair.py (words
PDFKit ran together), match.py (typeset words back to the prose).

A PDF older than the .tex is used anyway and said to be out of date;
findings it cannot match to the source (the text has changed since) are
counted, not shown.
"""

from ... import pdfwords
from ...findings import Finding, Skipped
from .find import Hit, find, part_text
from .match import align, pdf_tokens, title_words
from .repair import unglue
from .words import TOKEN, normal

NAME = "layout"
TITLE = "Layout"
BLURB = "line breaks in the typeset PDF"

__all__ = ["Skipped", "find", "run", "unglue"]


def run(prose, settings) -> list[Finding]:
    if settings.pdf is None:
        raise Skipped("no PDF beside the .tex (typeset it first)")
    try:
        pages = pdfwords.read(settings.pdf, say=settings.progress)
    except pdfwords.Unreadable as err:
        raise Skipped(str(err)) from err

    settings.progress("Layout: matching the typeset lines to the source")
    text = prose.text
    spans = [m.span() for m in TOKEN.finditer(text)]
    tokens = [normal(text[a:b]) for a, b in spans]
    pages = unglue(pages, set(tokens))
    pdf = pdf_tokens(pages)
    mapping = align([t for t, _ in pdf], tokens)
    parts = [part_text(text[a:b]) for a, b in prose.parts]
    hits = find(pages, title_words(pdf, mapping, spans, prose.titles), parts)

    first = _first_token(pdf, mapping)
    findings = [_finding(hit, span) for hit in hits if (span := _span(hit, first, spans, prose))]
    settings.stats[NAME] = {"unmatched": len(hits) - len(findings), "stale": settings.pdf_stale}
    return findings


def _span(hit: Hit, first: dict[int, int], spans, prose) -> tuple[int, int] | None:
    """Where in the prose a hit points: a part page at its \\part title (a
    short title may match nothing word for word), the rest at their word."""
    if hit.part is not None:
        return prose.parts[hit.part]
    at = first.get(id(hit.word))
    return None if at is None else spans[at]


def _first_token(pdf, mapping: dict[int, int]) -> dict[int, int]:
    """id() of each typeset word → the first prose token it maps to."""
    first: dict[int, int] = {}
    for index, (_, word) in enumerate(pdf):
        if index in mapping:
            first.setdefault(id(word), mapping[index])
    return first


def _finding(hit: Hit, span: tuple[int, int]) -> Finding:
    return Finding(NAME, *span, hit.message,
                   note=f"PDF page {hit.page + 1}, line {hit.line}", group=hit.kind)
