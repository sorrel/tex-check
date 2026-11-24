"""A status line on the terminal while a slow step runs.

A first check of a long book can take a minute or more (reading every
letter of the PDF, asking macOS's dictionary), and a silent terminal looks
stuck. So each step says what it is doing; if it is still going after
SHOW_AFTER seconds, one line on stderr shows it with a running count
(the PDF is read only once per typesetting, then cached):

    ⏳ Layout: first read of document.pdf since typesetting (a minute or two) · 12 s

The line is redrawn in place and wiped when the work is done, so the report
prints on a clean terminal. It is shown only on a terminal: --json, pipes
and tests see nothing.
"""

import shutil
import threading
import time
from collections.abc import Callable
from typing import Self, TextIO

#: Seconds a step runs before its line appears: quick steps never flash.
SHOW_AFTER = 1.0
#: How often the line is redrawn, in seconds.
TICK = 0.5
_CLEAR = "\r\033[K"  # back to the start of the line, and erase it


class Progress:
    """`say(text)` names the current step; a background thread draws it.

    Use as a context manager, so the line is always wiped at the end.
    """

    def __init__(self, stream: TextIO, enabled: bool = True,
                 clock: Callable[[], float] = time.monotonic, threaded: bool = True):
        self.stream = stream
        self.enabled = enabled
        self.clock = clock
        self._text = ""
        self._since = clock()
        self._shown = False          # a line is on the screen, to be wiped
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True) if threaded and enabled else None

    def __enter__(self) -> Self:
        if self._thread:
            self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def say(self, text: str) -> None:
        """The step now running; its clock starts now."""
        with self._lock:
            self._text, self._since = text, self.clock()

    def draw(self) -> None:
        """Show the current step, if it has been running long enough."""
        if not self.enabled:
            return
        with self._lock:
            elapsed = self.clock() - self._since
            if not self._text or elapsed < SHOW_AFTER:
                return
            count = f" · {elapsed:.0f} s"
            # One row only: a line that wraps cannot be wiped in place.
            room = shutil.get_terminal_size((80, 20)).columns - len(count) - 3
            text = self._text if len(self._text) <= room else self._text[: room - 1] + "…"
            self.stream.write(f"{_CLEAR}⏳ {text}{count}")
            self.stream.flush()
            self._shown = True

    def close(self) -> None:
        """Stop drawing and wipe the line."""
        self._done.set()
        if self._thread and self._thread.is_alive():
            self._thread.join()
        with self._lock:
            if self._shown:
                self.stream.write(_CLEAR)
                self.stream.flush()
                self._shown = False

    def _loop(self) -> None:
        while not self._done.wait(TICK):
            self.draw()
