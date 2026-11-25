"""LanguageTool, run on this Mac: started on demand, asked over HTTP.

The Homebrew package (`brew install languagetool`) brings its own Java and
a `languagetool-server` launcher. The first check of a run starts it on a
free port on 127.0.0.1 (it listens only there unless told `--public`,
which is never passed), and every later check in the process reuses it:
`--web` re-checks on each save without waiting for Java again. It stops
when tex-check exits. Nothing is sent off the machine; the public API is
never used.

The launcher runs under a small shell watchdog that holds a pipe from
tex-check: if tex-check dies without cleaning up (killed, crashed), the
pipe closes, the watchdog's `read` returns and it stops the server, so no
Java process is left behind.
"""

import atexit
import json
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

START_TIMEOUT = 90.0   # seconds for Java to start and load English; usually 3-5
CHECK_TIMEOUT = 120.0  # seconds for one request
INSTALL = "brew install languagetool"

#: Never through a proxy: an http_proxy setting would otherwise carry the
#: book's text off the machine, even to 127.0.0.1.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

#: Runs the launcher ($0, with its arguments) in the background, then
#: waits on stdin: EOF (tex-check gone, or closing the pipe) stops it.
_WATCHDOG = '"$0" "$@" & server=$!; read _; kill "$server" 2>/dev/null; wait'


class Unavailable(RuntimeError):
    """LanguageTool is not installed, would not start, or did not answer."""


@dataclass
class Server:
    url: str
    process: subprocess.Popen

    def stop(self) -> None:
        if self.process.poll() is None:
            try:
                self.process.stdin.close()   # the watchdog stops the server
                self.process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()


_server: Server | None = None
_lock = threading.Lock()


def server() -> Server:
    """The running local server, started if need be. Raises Unavailable."""
    global _server
    with _lock:
        if _server is not None and _server.process.poll() is None:
            return _server
        launcher = shutil.which("languagetool-server")
        if launcher is None:
            raise Unavailable(f"LanguageTool is not installed ({INSTALL})")
        _server = _start(launcher)
        atexit.register(_server.stop)
        return _server


def _start(launcher: str) -> Server:
    port = _free_port()
    process = subprocess.Popen(
        ["/bin/sh", "-c", _WATCHDOG, launcher, "--port", str(port)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    started = Server(f"http://127.0.0.1:{port}", process)
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise Unavailable("LanguageTool's server stopped as it started")
        try:
            with _OPENER.open(f"{started.url}/v2/languages", timeout=2):
                return started
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    started.stop()
    raise Unavailable(f"LanguageTool's server did not start within {START_TIMEOUT:.0f} s")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def check(text: str, language: str = "en-GB", disabled_rules: tuple[str, ...] = (),
          disabled_categories: tuple[str, ...] = ()) -> list[dict]:
    """LanguageTool's matches for `text`, as /v2/check returns them."""
    form = {"text": text, "language": language}
    if disabled_rules:
        form["disabledRules"] = ",".join(disabled_rules)
    if disabled_categories:
        form["disabledCategories"] = ",".join(disabled_categories)
    request = urllib.request.Request(f"{server().url}/v2/check",
                                     urllib.parse.urlencode(form).encode())
    try:
        with _OPENER.open(request, timeout=CHECK_TIMEOUT) as reply:
            return json.load(reply)["matches"]
    except (OSError, urllib.error.URLError, ValueError, KeyError) as err:
        raise Unavailable(f"LanguageTool did not answer: {err}") from err
