"""The action log beside each book: every OK mark and word-list add.

`tex-check-done.jsonl` holds one JSON object per line, appended and never
rewritten. It is the single record of what was decided, so the OK marks
are read from it and can never disagree with the history; and a wrong
button press can always be found again and undone. Undo is an entry too
(`{"action": "undo", "target": id}`), so the history stays whole.

An OK mark covers one place: it matches a finding by stage, flagged text
and the source-line context around it, never by line number, so it
survives edits elsewhere and lapses if that sentence is rewritten. Two
identical sentences share a mark, which is the price of not using lines.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

LOG_NAME = "tex-check-done.jsonl"

#: What an OK mark is matched on.
Fingerprint = tuple[str, str, str]


@dataclass(frozen=True)
class Entry:
    id: str
    at: str
    action: str  # "ok", "book", "personal" or "undo"
    stage: str = ""
    word: str | None = None
    message: str = ""
    text: str = ""
    context: str = ""
    line: int = 0
    target: str = ""  # for "undo": the entry undone
    added: bool = True  # for adds: whether the word was new to the list


_FIELDS = {f.name for f in fields(Entry)}


def log_file(tex: Path) -> Path:
    return tex.parent / LOG_NAME


def fingerprint(stage: str, text: str, context: str) -> Fingerprint:
    return (stage, text, context)


def record(path: Path, **values) -> Entry:
    """Append an entry and return it."""
    entry = Entry(
        id=secrets.token_urlsafe(9),
        at=datetime.now().isoformat(timespec="minutes"),
        **values,
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    return entry


def entries(path: Path) -> list[Entry]:
    """Every readable entry, oldest first. Lines that are not an entry are skipped."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or "id" not in data or "action" not in data:
            continue
        try:
            out.append(Entry(**{k: v for k, v in data.items() if k in _FIELDS}))
        except TypeError:
            continue
    return out


def undone(all_entries: list[Entry]) -> set[str]:
    return {e.target for e in all_entries if e.action == "undo"}


def ok_marks(path: Path) -> set[Fingerprint]:
    """The places marked OK and not since undone."""
    all_entries = entries(path)
    gone = undone(all_entries)
    return {
        fingerprint(e.stage, e.text, e.context)
        for e in all_entries
        if e.action == "ok" and e.id not in gone
    }
