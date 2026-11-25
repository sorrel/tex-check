"""The checking stages, in the order they run.

Each stage is a module with NAME, TITLE, BLURB and run(prose, settings).
To add a stage, write the module and add it to STAGES.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import grammar, languagetool, layout, near_repeats, punctuation, repeats, spelling

STAGES = [repeats, near_repeats, punctuation, spelling, grammar, languagetool, layout]
BY_NAME = {stage.NAME: stage for stage in STAGES}
ALIASES = {"repeat": "repeats", "near": "near-repeats", "punct": "punctuation", "spell": "spelling", "grammar": "grammar", "lt": "languagetool"}


def _quiet(_: str) -> None:
    """The default progress: say nothing."""


@dataclass
class Settings:
    """Options the stages read. The CLI fills this in."""

    dictionary: str = "en_GB-ise"
    wordlists: list[Path] = field(default_factory=list)
    spell_bold_names: bool = False
    spell_capitals: bool = False
    places: set[str] | None = None  # gazetteer; None when not downloaded
    british: bool = True  # ask the larger British list (if downloaded)
    macos: bool = True  # ask macOS's British spellchecker
    pdf: Path | None = None  # the typeset book beside the .tex, for layout
    pdf_stale: bool = False  # the PDF is older than the .tex
    stats: dict = field(default_factory=dict)  # stages leave figures here for the report
    #: Names the step now running, for the terminal's status line (progress.py).
    progress: Callable[[str], None] = _quiet


def resolve(names: list[str]) -> list:
    """Stage modules for the given names (aliases allowed), in run order."""
    wanted = set()
    for name in names:
        key = ALIASES.get(name, name)
        if key not in BY_NAME:
            choices = ", ".join(BY_NAME)
            raise ValueError(f"unknown stage '{name}' (choose from {choices})")
        wanted.add(key)
    return [stage for stage in STAGES if stage.NAME in wanted]
