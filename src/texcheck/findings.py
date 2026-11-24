"""The one record type every check produces."""

from dataclasses import dataclass, field


@dataclass
class Finding:
    """A problem at a span of the extracted prose.

    `start`/`end` index the Prose text; the report maps them back to the
    source. `group` lets a stage collapse many findings into one row (the
    spelling stage groups by word).
    """

    stage: str
    start: int
    end: int
    message: str
    note: str = ""
    suggestions: list[str] = field(default_factory=list)
    group: str = ""


class Skipped(RuntimeError):
    """A stage could not run here (no aspell, no PDF); the message says why."""
