"""Word positions from the typeset PDF, for the layout checks.

Lone "I"s at line edges, stacked words and one-word last lines depend on
where TeX broke the lines, which only the PDF knows. macOS's PDFKit gives
exact positions: one `osascript` call (JavaScript for Automation) reads
every letter's box and builds the words from the gaps between them, about
a minute and a half for a 290-page book. The result is cached by the PDF's size and modification time, so a
re-check is instant until the book is typeset again.

pdftotext (xpdf) and pdftohtml give positions per line at best, which is
not enough to tell which word sits above which.
"""

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .places import data_dir

TIMEOUT = 600  # seconds; a 290-page book takes about 90

_SCRIPT = r"""
ObjC.import('PDFKit');
// Words are built from each letter's own selection box, not from the page's
// text and characterBoundsAtIndex: LuaTeX writes no space characters, PDFKit's
// guessed spaces are sometimes missing (a whole line as one "word"), and the
// fast per-index boxes are sometimes too wide to show the gap between words.
function run(argv) {
  const doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  if (doc.isNil()) throw new Error("cannot open the PDF");
  const GAP = 1.0;   // points between letters that makes a new word
  const pages = [];
  for (let p = 0; p < doc.pageCount; p++) {
    const page = doc.pageAtIndex(p);
    const words = [];
    let cur = null;
    const flush = () => {
      if (cur) words.push([cur.t, +cur.x0.toFixed(1), +cur.x1.toFixed(1), +cur.y.toFixed(1)]);
      cur = null;
    };
    for (let k = 0; k < page.numberOfCharacters; k++) {
      const sel = page.selectionForRange($.NSMakeRange(k, 1));
      if (sel.isNil()) continue;
      const c = sel.string.js;
      if (!c || /\s/.test(c)) { flush(); continue; }
      const b = sel.boundsForPage(page);
      const x0 = b.origin.x, x1 = b.origin.x + b.size.width, y = b.origin.y;
      if (b.size.width <= 0 && x0 === 0 && y === 0) continue;   // not on the page
      if (cur && c === cur.last && x0 === cur.lx0) continue;    // a line break repeats the letter
      if (cur && (Math.abs(y - cur.y) > 3 || x0 - cur.x1 > GAP || x0 < cur.x0)) flush();
      if (!cur) cur = {t: "", x0: x0, x1: x1, y: y};
      cur.t += c;
      cur.x1 = Math.max(cur.x1, x1);
      cur.last = c;
      cur.lx0 = x0;
    }
    flush();
    pages.push(words);
  }
  return JSON.stringify(pages);
}
"""


class Unreadable(RuntimeError):
    """The PDF's words could not be read (not macOS, or PDFKit failed)."""


@dataclass(frozen=True)
class Word:
    text: str
    x0: float  # left edge, points
    x1: float  # right edge
    y: float   # height on the page (PDF points, from the bottom)


Line = list[Word]


def lines_of(words: list[Word], tolerance: float = 4.0) -> list[Line]:
    """Group a page's words, in reading order, into lines.

    A new line starts when the height changes by more than `tolerance`
    points or the text goes back to the left (a descender can shift y).
    """
    lines: list[Line] = []
    for word in words:
        line = lines[-1] if lines else None
        if line and abs(word.y - line[0].y) <= tolerance and word.x0 > line[-1].x0:
            line.append(word)
        else:
            lines.append([word])
    return lines


def _cache_file(pdf: Path, cache: Path) -> Path:
    stat = pdf.stat()
    key = hashlib.sha256(f"{pdf.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()
    return cache / f"{key[:24]}.json"


def read(pdf: Path, cache: Path | None = None, run: Callable = subprocess.run,
         platform: str = sys.platform,
         say: Callable[[str], None] = lambda _: None) -> list[list[Word]]:
    """Every page's words, in reading order. Raises Unreadable.

    `say` is told when the slow part starts: reading a PDF not yet cached.
    """
    if platform != "darwin":
        raise Unreadable("the layout checks need macOS (PDFKit)")
    cache = cache or data_dir() / "layout-cache"
    stored = _cache_file(pdf, cache)
    if stored.is_file():
        raw = stored.read_text(encoding="utf-8")
    else:
        say(f"Layout: first read of {pdf.name} since typesetting (a minute or two)")
        try:
            result = run(["osascript", "-l", "JavaScript", "-", str(pdf)], input=_SCRIPT,
                         capture_output=True, text=True, timeout=TIMEOUT, check=False)
        except (OSError, subprocess.SubprocessError) as err:
            raise Unreadable(f"could not read the PDF: {err}") from err
        if result.returncode != 0:
            raise Unreadable(f"could not read the PDF: {result.stderr.strip()[:200]}")
        raw = result.stdout
        cache.mkdir(parents=True, exist_ok=True)
        for old in cache.glob("*.json"):  # keep one book's worth per PDF, not every version
            if old != stored and _same_pdf(old, pdf):
                old.unlink(missing_ok=True)
                old.with_suffix(".src").unlink(missing_ok=True)
        stored.write_text(raw, encoding="utf-8")
        stored.with_suffix(".src").write_text(str(pdf.resolve()), encoding="utf-8")
    try:
        return [[Word(t, x0, x1, y) for t, x0, x1, y in page] for page in json.loads(raw)]
    except (ValueError, TypeError) as err:
        raise Unreadable(f"could not read the PDF: {err}") from err


def _same_pdf(cached: Path, pdf: Path) -> bool:
    src = cached.with_suffix(".src")
    return src.is_file() and src.read_text(encoding="utf-8") == str(pdf.resolve())
