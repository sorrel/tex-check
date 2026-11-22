"""The checking stages, in the order they run.

Each stage is a module with NAME, TITLE, BLURB and run(prose, settings).
To add a stage, write the module and add it to STAGES.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import grammar, punctuation, repeats, spelling

STAGES = [repeats, punctuation, spelling, grammar]
BY_NAME = {stage.NAME: stage for stage in STAGES}
ALIASES = {"repeat": "repeats", "punct": "punctuation", "spell": "spelling", "grammar": "grammar"}


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
    stats: dict = field(default_factory=dict)  # stages leave figures here for the report


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
