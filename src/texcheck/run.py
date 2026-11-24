"""One check of one file: the run the terminal report, --json and the browser share.

Keeping it in one place is what makes the three views agree. In particular
the word lists are read afresh on every run, so a word added in the browser
counts at the next re-check, and the terminal sees it too.
"""

from dataclasses import dataclass, field
from pathlib import Path

from . import wordlists
from .checks import Settings
from .findings import Finding, Skipped
from .latex import extract
from .prose import Prose, Source


@dataclass(frozen=True)
class Options:
    """What the command line chose; the same for every run of a session."""

    dictionary: str = "en_GB-ise"
    extra_wordlists: tuple[Path, ...] = ()
    spell_bold: bool = False
    spell_capitals: bool = False
    personal_words: bool = True
    british: bool = True
    macos: bool = True


class Located:
    """A finding with its source position worked out."""

    def __init__(self, finding: Finding, prose: Prose, source: Source):
        self.finding = finding
        self.start, self.end = prose.source_span(finding.start, finding.end)
        self.line, self.col = source.line_col(self.start)
        self.end_line, self.end_col = source.line_col(self.end)
        self.text = source.text[self.start : self.end]

    def where(self, path: str) -> str:
        return f"{path}:{self.line}:{self.col}"


#: Characters of context either side of a finding.
CONTEXT = 38
#: The width context is cut to when it is used to recognise a place (OK marks).
CONTEXT_WIDTH = 110


def snippet_parts(source: Source, loc: Located, width: int) -> tuple[bool, str, str, str, bool]:
    """The source line around a finding, as plain text.

    Returns (cut on the left, before, hit, after, cut on the right). The
    browser view uses the parts as they are; `snippet` styles them.
    """
    line = source.line_text(loc.line)
    left = loc.col - 1
    right = min(len(line), left + max(1, loc.end - loc.start))
    room = max(20, (width - (right - left)) // 2)
    lo, hi = max(0, left - min(CONTEXT, room)), min(len(line), right + min(CONTEXT, room))
    before, hit, after = line[lo:left], line[left:right], line[right:hi]
    if not hit.strip():  # make whitespace visible
        hit = hit.replace(" ", "␣").replace("\t", "⇥")
    before, hit, after = (part.replace("\t", " ") for part in (before, hit, after))
    return lo > 0, before, hit, after, hi < len(line)


def context_of(source: Source, loc: Located) -> str:
    """The context around a finding, with the finding bracketed: what an
    OK mark is matched on. The brackets tell apart two uses of a word on
    one short line, whose windows would otherwise be the same text."""
    _, before, hit, after, _ = snippet_parts(source, loc, CONTEXT_WIDTH)
    return f"{before}[[{hit}]]{after}"


@dataclass
class Run:
    """A file, as read, and what each stage made of it.

    `results` pairs each stage module with its findings, or with a string
    saying why it was skipped (aspell missing, say).
    """

    path: Path
    source: Source
    prose: Prose
    results: list[tuple[object, list[Finding] | str]]
    stats: dict = field(default_factory=dict)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def settings_for(path: Path, options: Options, gazetteer: set[str] | None) -> Settings:
    pdf = path.with_suffix(".pdf")  # the typeset book, for the layout checks
    lists = [wordlists.book_file(path)]
    if options.personal_words:
        lists.append(wordlists.personal_file())
    return Settings(
        dictionary=options.dictionary,
        wordlists=[f for f in lists if f.is_file()] + list(options.extra_wordlists),
        spell_bold_names=options.spell_bold,
        spell_capitals=options.spell_capitals,
        places=gazetteer,
        british=options.british,
        macos=options.macos,
        pdf=pdf if pdf.is_file() else None,
        pdf_stale=pdf.is_file() and pdf.stat().st_mtime < path.stat().st_mtime,
    )


def check_file(path: Path, stages: list, options: Options, gazetteer: set[str] | None) -> Run:
    """Read `path` and run `stages` over it. Raises OSError if it cannot be read."""
    source = Source(read(path), str(path))
    prose = extract(source.text)
    settings = settings_for(path, options, gazetteer)
    results: list[tuple[object, list[Finding] | str]] = []
    for stage in stages:
        try:
            results.append((stage, stage.run(prose, settings)))
        except Skipped as err:
            results.append((stage, str(err)))
    return Run(path, source, prose, results, settings.stats)
