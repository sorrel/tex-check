"""The browser view's state, held in memory for the life of the process.

Findings are addressed by opaque ids, made afresh at every check (the
mail-triage pattern). A page left open across a re-check therefore cannot
name a finding by an old position and open Texifier at the wrong line: its
ids are simply unknown, and the page is told to reload.

Nothing here is persisted except words added to a list.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .. import wordlists
from ..groups import Group, Item, group_findings
from ..opener import open_at
from ..report import snippet_parts
from ..run import Located, Options, Run, check_file
from .watcher import Debouncer, Watcher

#: Characters of context the page shows, as a terminal of this width would.
CONTEXT_WIDTH = 110

SCOPES = ("book", "personal")


class StaleId(LookupError):
    """An id from an earlier check, or one never issued."""


class Session:
    def __init__(self, path: Path, stages: list, options: Options, gazetteer: set[str] | None,
                 opener: Callable[[Path, int, int], str | None] = open_at,
                 clock: Callable[[], float] = time.monotonic):
        self.path = path
        self.stages = stages
        self.options = options
        self.gazetteer = gazetteer
        self.opener = opener
        self.clock = clock
        self.version = 0
        self.error: str | None = None
        self.checking = False
        self._lock = threading.Lock()  # guards the findings below
        self._check_lock = threading.Lock()  # one check at a time
        self._check()  # an unreadable file at start-up is the caller's to report
        self.watcher = Watcher(self._watched, Debouncer(clock=clock), self.recheck)

    def _watched(self) -> list[Path]:
        return [self.path, wordlists.book_file(self.path), wordlists.personal_file()]

    # ── checking ────────────────────────────────────────────────────────────

    def _check(self) -> None:
        run = check_file(self.path, self.stages, self.options, self.gazetteer)
        groups = group_findings(run)
        items = {secrets.token_urlsafe(9): item for group in groups for item in group.items}
        uses = {secrets.token_urlsafe(9): use for item in items.values() for use in item.uses}
        with self._lock:
            self._run: Run = run
            self._groups: list[Group] = groups
            self._items: dict[str, Item] = items
            self._item_ids = {id(item): key for key, item in items.items()}
            self._uses: dict[str, Located] = uses
            self._use_ids = {id(use): key for key, use in uses.items()}
            self.version += 1
            self.checked_at = datetime.now().strftime("%H:%M")

    def recheck(self) -> None:
        """Check the file again. On failure, keep the findings and say why."""
        self.watcher.debouncer.cancel()
        with self._check_lock:
            self.checking = True
            try:
                self._check()
                self.error = None
            except Exception as err:  # noqa: BLE001: shown on the page, never fatal
                self.error = f"could not check {self.path.name}: {err}"
            finally:
                self.checking = False

    # ── what the page is told ───────────────────────────────────────────────

    def status(self) -> dict:
        left = self.watcher.debouncer.seconds_left()
        state = "checking" if self.checking else "waiting" if left is not None else "idle"
        return {
            "version": self.version,
            "state": state,
            "seconds_left": None if left is None else round(left),
            "error": self.error,
        }

    def findings(self) -> dict:
        with self._lock:
            return {
                "version": self.version,
                "file": self.path.name,
                "checked_at": self.checked_at,
                "groups": [self._group_payload(group) for group in self._groups],
            }

    def _group_payload(self, group: Group) -> dict:
        return {
            "key": group.key, "title": group.title, "blurb": group.blurb,
            "skipped": group.skipped, "count": len(group.items),
            "items": [self._item_payload(item) for item in group.items],
        }

    def _item_payload(self, item: Item) -> dict:
        return {
            "id": self._item_ids[id(item)], "word": item.word, "message": item.message,
            "note": item.note, "suggestions": item.suggestions,
            "uses": [self._use_payload(use) for use in item.uses],
        }

    def _use_payload(self, use: Located) -> dict:
        cut_left, before, hit, after, cut_right = snippet_parts(
            self._run.source, use, CONTEXT_WIDTH
        )
        return {
            "id": self._use_ids[id(use)], "line": use.line, "col": use.col,
            "before": before, "hit": hit, "after": after,
            "cut_left": cut_left, "cut_right": cut_right,
        }

    # ── acting ──────────────────────────────────────────────────────────────

    def open(self, use_id: str) -> str | None:
        """Open Texifier at a use. Returns None, or why it could not."""
        with self._lock:
            use = self._uses.get(use_id)
        if use is None:
            raise StaleId(use_id)
        return self.opener(self.path, use.line, use.col)

    def add_word(self, item_id: str, scope: str) -> list[str]:
        """Add an item's word to the book's or the personal list.

        Every item with that word leaves the page at once, without waiting
        for a re-check. Returns their ids.
        """
        if scope not in SCOPES:
            raise ValueError(f"unknown word list {scope!r}")
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                raise StaleId(item_id)
            if not item.word:
                raise ValueError("only misspelt words can go in a word list")
            target = wordlists.book_file(self.path) if scope == "book" else wordlists.personal_file()
            wordlists.append_word(target, item.word)
            same = wordlists.normalise(item.word).lower()
            removed = []
            for group in self._groups:
                keep = []
                for other in group.items:
                    if other.word and wordlists.normalise(other.word).lower() == same:
                        removed.append(self._item_ids[id(other)])
                    else:
                        keep.append(other)
                group.items = keep
        self.watcher.rebaseline()
        return removed
