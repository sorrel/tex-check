"""The socket half of the browser view (adapted from mail-triage's).

Everything that needs a real port lives here and nothing else does, which is
what lets the routing be tested as a pure function. Three things matter:

- **Bind 127.0.0.1**, never 0.0.0.0 or ::. The strict ``Host`` check in
  ``security`` is what stops a rebinding attack from routing around it.
- **Log nothing.** ``BaseHTTPRequestHandler`` writes a line per request to
  stderr by default; the page polls every two seconds, so that would bury
  the terminal, and put the opening URL, token and all, in its scrollback.
- **Stop when idle.** The page polls while it is open, so half an hour
  without a request means the tab has gone; the process should go too.
"""

import threading
import time
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TextIO
from urllib.parse import parse_qsl, urlsplit

from .routes import Router
from .security import Request

#: A request names one id; anything this large is a mistake or an attempt at one.
MAX_BODY_BYTES = 100_000
IDLE_TIMEOUT_SECONDS = 1800.0
DEFAULT_PORT = 8766  # mail-triage has 8765


def build_handler(router: Router) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        # Content-Length is set on every response, so keep-alive is safe.
        protocol_version = "HTTP/1.1"

        def log_message(self, *args, **kwargs) -> None:
            """Deliberately silent: see the module docstring."""

        def _respond(self) -> None:
            if (request := self._read_request()) is None:
                self.send_response(413)  # the body is too large to read
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            response = router.handle(request)
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            for name, value in response.extra_headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response.body)

        def _read_request(self) -> Request | None:
            """The request as the router sees it, or None if its body is too big."""
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > MAX_BODY_BYTES:
                return None
            parts = urlsplit(self.path)
            return Request(
                method=self.command,
                path=parts.path,
                query=dict(parse_qsl(parts.query)),
                headers=dict(self.headers),
                body=self.rfile.read(length) if length else b"",
            )

        do_GET = _respond
        do_POST = _respond

    return Handler


#: What to type in the terminal to stop the server, then Return.
QUIT_WORDS = frozenset({"q", "quit", "exit"})


def listen_for_quit(stream: TextIO, stop: Callable[[], None]) -> None:
    """Read lines until one is a quit word, then call `stop`. Returns at EOF."""
    for line in stream:
        if line.strip().lower() in QUIT_WORDS:
            stop()
            return


def _stop_when_idle(server: ThreadingHTTPServer, router: Router, idle_timeout: float) -> None:
    """Shut the server down once no request has come for `idle_timeout` seconds."""
    while True:
        time.sleep(5)
        if time.monotonic() - router.last_request > idle_timeout:
            server.shutdown()
            return


def serve(router: Router, port: int = DEFAULT_PORT, open_browser: bool = True,
          idle_timeout: float = IDLE_TIMEOUT_SECONDS,
          on_ready: Callable[[str, int, Callable[[], None]], None] | None = None,
          keyboard: TextIO | None = None) -> None:
    """Serve until Ctrl-C, or `idle_timeout` seconds without a request.

    Raises OSError if the port is taken. `on_ready` is told the URL, the
    port actually bound (for port 0) and a function that stops the server.
    With `keyboard` (the terminal), typing q, quit or exit stops it too.
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), build_handler(router))
    actual_port = server.server_address[1]
    router.port = actual_port  # the Host check must name the port really bound
    url = f"http://127.0.0.1:{actual_port}/?k={router.token}"
    watcher = router.session.watcher

    threading.Thread(target=_stop_when_idle, args=(server, router, idle_timeout), daemon=True).start()
    if keyboard is not None:
        threading.Thread(target=listen_for_quit, args=(keyboard, server.shutdown), daemon=True).start()
    watcher.start()
    if on_ready is not None:
        on_ready(url, actual_port, server.shutdown)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        server.server_close()
