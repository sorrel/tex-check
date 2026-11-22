"""One check of one file: the run the terminal report, --json and the browser share.

Keeping it in one place is what makes the three views agree. In particular
the word lists are read afresh on every run, so a word added in the browser
counts at the next re-check, and the terminal sees it too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import wordlists
from .checks import Settings
from .checks.spelling import SpellerMissing
from .findings import Finding
from .prose import Prose, Source, extract


@dataclass(frozen=True)
class Options:
    """What the command line chose; the same for every run of a session."""

    dictionary: str = "en_GB-ise"
    extra_wordlists: tuple[Path, ...] = ()
    spell_bold: bool = False
    spell_capitals: bool = False
    personal_words: bool = True


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
    lists = [wordlists.book_file(path)]
    if options.personal_words:
        lists.append(wordlists.personal_file())
    return Settings(
        dictionary=options.dictionary,
        wordlists=[f for f in lists if f.is_file()] + list(options.extra_wordlists),
        spell_bold_names=options.spell_bold,
        spell_capitals=options.spell_capitals,
        places=gazetteer,
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
        except SpellerMissing as err:
            results.append((stage, str(err)))
    return Run(path, source, prose, results, settings.stats)
