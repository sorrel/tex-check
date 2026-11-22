"""Re-check after edits settle: 30 seconds after the last save, not every save.

Saving several times in quick succession while fixing typos should not set
off a check per save, each redrawing the page under the cursor. So a save
only (re)starts a countdown, and the check runs once it reaches zero.

Saves are noticed by polling modification times once a second. That needs
no dependencies and copes with editors that save by replacing the file,
which defeats watching the file itself.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

#: Seconds of quiet after a save before the file is checked again.
DELAY = 30.0


class Debouncer:
    """A countdown that every `touch` restarts and that fires once."""

    def __init__(self, delay: float = DELAY, clock: Callable[[], float] = time.monotonic):
        self.delay = delay
        self.clock = clock
        self._deadline: float | None = None

    def touch(self) -> None:
        self._deadline = self.clock() + self.delay

    def cancel(self) -> None:
        self._deadline = None

    def seconds_left(self) -> float | None:
        if self._deadline is None:
            return None
        return max(0.0, self._deadline - self.clock())

    def due(self) -> bool:
        """True once, when the countdown has run out."""
        if self._deadline is None or self.clock() < self._deadline:
            return False
        self._deadline = None
        return True


def _mtime(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


class Watcher:
    """Polls files for saves and calls `on_due` when the countdown runs out.

    `paths` is asked afresh each poll, so a word list created later is seen.
    A file appearing or disappearing counts as a save.
    """

    def __init__(self, paths: Callable[[], list[Path]], debouncer: Debouncer,
                 on_due: Callable[[], None], interval: float = 1.0):
        self.paths = paths
        self.debouncer = debouncer
        self.on_due = on_due
        self.interval = interval
        self._last = self._snapshot()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _snapshot(self) -> dict[Path, int | None]:
        return {path: _mtime(path) for path in self.paths()}

    def rebaseline(self) -> None:
        """Take the files as they are now, without counting it as a save.

        For writes the session makes itself (adding a word), which are not
        edits that need a re-check.
        """
        self._last = self._snapshot()

    def poll(self) -> None:
        """One step: notice a save, and fire if the countdown has run out."""
        now = self._snapshot()
        if now != self._last:
            self._last = now
            self.debouncer.touch()
        if self.debouncer.due():
            self.on_due()

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self.interval):
                self.poll()

        self._thread = threading.Thread(target=loop, name="tex-check-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
