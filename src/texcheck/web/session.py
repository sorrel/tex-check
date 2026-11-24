"""The browser view's state, held in memory for the life of the process.

Findings are addressed by opaque ids, made afresh at every check (the
mail-triage pattern). A page left open across a re-check therefore cannot
name a finding by an old position and open Texifier at the wrong line: its
ids are simply unknown, and the page is told to reload.

What is persisted lives beside the book: words added to a list, and every
action (OK, add, undo) in the done log (see donelog), which is also where
OK marks are read from.
"""

import secrets
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .. import donelog, wordlists
from ..differences import describe, marked
from ..groups import Group, Item, group_findings
from ..opener import open_at
from ..run import (
    CONTEXT_WIDTH,
    Located,
    Options,
    Run,
    check_file,
    context_of,
    snippet_parts,
)
from .watcher import Debouncer, Watcher

SCOPES = ("book", "personal")


class StaleId(LookupError):
    """An id from an earlier check, or one never issued."""


class Session:
    def __init__(self, path: Path, stages: list, options: Options, gazetteer: set[str] | None,
                 opener: Callable[..., str | None] = open_at,
                 clock: Callable[[], float] = time.monotonic,
                 progress: Callable[[str], None] | None = None):
        self.path = path
        self.stages = stages
        self.options = options
        self.gazetteer = gazetteer
        self.opener = opener
        self.clock = clock
        self.version = 0
        self.error: str | None = None
        self.checking = False
        #: The step a re-check is on, and when it started, for the page.
        self._step: tuple[str, float] | None = None
        #: Every word added this session, in order. A check notes how many
        #: there were when it started, and drops any added while it ran:
        #: it read the lists before they were written.
        self._added: list[str] = []
        self._lock = threading.Lock()  # guards the findings below
        self._check_lock = threading.Lock()  # one check at a time
        # An unreadable file at start-up is the caller's to report. `progress`
        # shows this first check on the terminal; later ones show on the page.
        self._check(progress)
        self.watcher = Watcher(self._watched, Debouncer(clock=clock), self.recheck)

    def _watched(self) -> list[Path]:
        # The PDF too: typesetting again changes the layout findings.
        return [self.path, self.path.with_suffix(".pdf"), wordlists.book_file(self.path),
                wordlists.personal_file()]

    # ── checking ────────────────────────────────────────────────────────────

    @property
    def log(self) -> Path:
        return donelog.log_file(self.path)

    def _check(self, progress: Callable[[str], None] | None = None) -> None:
        added_before = len(self._added)
        run = check_file(self.path, self.stages, self.options, self.gazetteer, progress)
        with self._lock:
            late = set(self._added[added_before:])
        self._publish(run, late)

    def _publish(self, run: Run, late: set[str] = frozenset()) -> None:
        """Group a run's findings, leave out OK marks, and issue fresh ids.

        OK marks are read here, after the check, so one made while it ran
        still counts.
        """
        groups = group_findings(run, ok=donelog.ok_marks(self.log))
        if late:
            for group in groups:
                group.items = [i for i in group.items if not (i.word and _same(i.word) in late)]
        items = {secrets.token_urlsafe(9): item for group in groups for item in group.items}
        uses: dict[str, Located] = {}
        use_item: dict[str, Item] = {}
        for item in items.values():
            for use in item.uses:
                key = secrets.token_urlsafe(9)
                uses[key] = use
                use_item[key] = item
        with self._lock:
            self._use_item: dict[str, Item] = use_item
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
                self._check(self._note_step)
                self.error = None
            except Exception as err:  # shown on the page, never fatal
                self.error = f"could not check {self.path.name}: {err}"
            finally:
                self.checking = False
                self._step = None

    def _note_step(self, text: str) -> None:
        self._step = (text, self.clock())

    # ── what the page is told ───────────────────────────────────────────────

    def status(self) -> dict:
        left = self.watcher.debouncer.seconds_left()
        state = "checking" if self.checking else "waiting" if left is not None else "idle"
        step = self._step if self.checking else None
        return {
            "version": self.version,
            "state": state,
            "seconds_left": None if left is None else round(left),
            "error": self.error,
            # What a re-check is doing, and for how long (a first read of a
            # PDF takes a minute or two).
            "step": step and step[0],
            "step_seconds": step and round(self.clock() - step[1]),
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
            "skipped": group.skipped, "count": len(group.items), "section": group.section,
            "items": [self._item_payload(item) for item in group.items],
        }

    def _item_payload(self, item: Item) -> dict:
        return {
            "id": self._item_ids[id(item)], "word": item.word, "message": item.message,
            "note": item.note, "reason": item.reason,
            "suggestions": [_suggestion(item.word, s) for s in item.suggestions]
            if item.word else item.suggestions,
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
        """Open Texifier at a use. Returns None, or why it could not.

        The phrase to find is taken from the text that was checked, so an
        edit since then cannot send Texifier to the wrong place.
        """
        with self._lock:
            use = self._uses.get(use_id)
        if use is None:
            raise StaleId(use_id)
        return self.opener(self.path, use.line, use.col, text=self._run.source.text)

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
            added = wordlists.append_word(target, item.word)
            self._record(scope, item, item.uses[0], added=added)
            same = _same(item.word)
            self._added.append(same)
            removed = []
            for group in self._groups:
                keep = []
                for other in group.items:
                    if other.word and _same(other.word) == same:
                        removed.append(self._item_ids[id(other)])
                    else:
                        keep.append(other)
                group.items = keep
            self.watcher.rebaseline(target)
        return removed


    def _record(self, action: str, item: Item, use: Located, added: bool = True) -> donelog.Entry:
        return donelog.record(
            self.log, action=action, stage=item.stage, word=item.word,
            message=item.message, text=use.text, context=context_of(self._run.source, use),
            line=use.line, added=added,
        )

    def ok(self, use_id: str) -> None:
        """Mark one use OK: it leaves the page at once and is logged."""
        with self._lock:
            use = self._uses.get(use_id)
            item = self._use_item.get(use_id)
            if use is None or item is None:
                raise StaleId(use_id)
            self._record("ok", item, use)
            item.uses = [u for u in item.uses if u is not use]
            for group in self._groups:
                if item in group.items:
                    group.hidden += 1
                    if not item.uses:
                        group.items = [i for i in group.items if i is not item]

    def done(self) -> list[dict]:
        """Every action, newest first, with whether it has been undone."""
        entries = donelog.entries(self.log)
        gone = donelog.undone(entries)
        return [
            {"id": e.id, "at": e.at, "action": e.action, "word": e.word,
             "message": e.message, "text": e.text, "line": e.line, "undone": e.id in gone}
            for e in reversed(entries) if e.action != "undo"
        ]

    def undo(self, entry_id: str) -> None:
        """Undo one action. Raises KeyError for an unknown entry; twice is harmless.

        An OK comes back at once. An add takes the word out of its list (only
        if this add put it there) and re-checks, since the word is unknown again.
        """
        entries = donelog.entries(self.log)
        entry = next((e for e in entries if e.id == entry_id and e.action != "undo"), None)
        if entry is None:
            raise KeyError(entry_id)
        if entry.id in donelog.undone(entries):
            return
        donelog.record(self.log, action="undo", target=entry.id)
        if entry.action == "ok":
            with self._check_lock:
                self._publish(self._run)
            return
        if entry.added and entry.word:
            target = wordlists.book_file(self.path) if entry.action == "book" else wordlists.personal_file()
            wordlists.remove_word(target, entry.word)
            self.watcher.rebaseline(target)
        self.recheck()


def _suggestion(word: str, suggestion: str) -> dict:
    """A suggestion with its changed letters marked and its difference in words."""
    return {
        "text": suggestion,
        "parts": [[text, changed] for text, changed in marked(word, suggestion)],
        "difference": describe(word, suggestion),
    }


def _same(word: str) -> str:
    """A word as the word lists compare it."""
    return wordlists.normalise(word).lower()
