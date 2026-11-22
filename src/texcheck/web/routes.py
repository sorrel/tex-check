"""Every route, as a pure function of a request.

No sockets and no globals live here, which is what lets the whole HTTP
surface be tested by building a ``Request`` and asserting on a ``Response``.
The socket is ``server``'s business.

The browser never names a file, a line or a word list: it names findings by
the opaque ids the session issued, and the session decides the rest. So
there is nothing a request could say that reaches outside this one book and
its two word lists.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
from pathlib import Path

from .security import (
    SECURITY_HEADERS,
    Request,
    Response,
    TokenGate,
    check_request,
    session_cookie,
)
from .session import Session, StaleId

TOKEN_PLACEHOLDER = "__TOKEN__"
STATIC_DIR = Path(__file__).parent / "static"

_STALE = "re-checked since this page was drawn; reload"


class Router:
    def __init__(self, session: Session, token: str, port: int, static_dir: Path = STATIC_DIR):
        self.session = session
        self.token = token
        self.port = port
        self.static_dir = static_dir
        self.gate = TokenGate(token)
        #: When the last request arrived, for the server's idle timeout.
        self.last_request = time.monotonic()

    def handle(self, request: Request) -> Response:
        self.last_request = time.monotonic()
        refused = check_request(request, self.gate, self.port)
        response = refused or self._route(request)
        headers = {**SECURITY_HEADERS, **response.extra_headers}
        return Response(response.status, response.body, response.content_type, headers)

    def _route(self, request: Request) -> Response:
        method, path = request.method, request.path
        if method == "GET" and (path == "/" or path.startswith("/static/")):
            return self._static(path)
        if method == "GET" and path == "/api/findings":
            return Response.json(self.session.findings())
        if method == "GET" and path == "/api/status":
            return Response.json(self.session.status())
        if method == "POST" and path == "/api/open":
            return self._open(request)
        if method == "POST" and path == "/api/words":
            return self._words(request)
        if method == "POST" and path == "/api/recheck":
            threading.Thread(target=self.session.recheck, daemon=True).start()
            return Response.json({"ok": True})
        return Response.json({"error": "no such route"}, status=404)

    def _open(self, request: Request) -> Response:
        body = _body(request)
        if body is None or not isinstance(body.get("use"), str):
            return Response.json({"error": "expected {\"use\": id}"}, status=400)
        try:
            error = self.session.open(body["use"])
        except StaleId:
            return Response.json({"error": _STALE}, status=409)
        return Response.json({"error": error} if error else {"ok": True})

    def _words(self, request: Request) -> Response:
        body = _body(request)
        if body is None or not isinstance(body.get("item"), str):
            return Response.json({"error": "expected {\"item\": id, \"scope\": …}"}, status=400)
        try:
            removed = self.session.add_word(body["item"], str(body.get("scope")))
        except StaleId:
            return Response.json({"error": _STALE}, status=409)
        except ValueError as err:
            return Response.json({"error": str(err)}, status=400)
        return Response.json({"removed": removed})

    def _static(self, path: str) -> Response:
        name = "index.html" if path == "/" else path.removeprefix("/static/")
        root = self.static_dir.resolve()
        target = (root / name).resolve()
        # Never serve a path that climbs out of the folder. resolve() first, so
        # "..", a symlink and an absolute path are all caught by one check.
        if root not in target.parents or not target.is_file():
            return Response.json({"error": "no such file"}, status=404)
        body = target.read_bytes()
        headers: dict[str, str] = {}
        if target.name == "index.html":
            # The page needs the token for the API and cannot be given it in a
            # header, so it is put in on the way out; the file never holds it.
            body = body.replace(TOKEN_PLACEHOLDER.encode(), self.token.encode())
            # And a cookie, so a reload works once the URL token is spent.
            headers["Set-Cookie"] = session_cookie(self.token)
        content_type, _ = mimetypes.guess_type(target.name)
        return Response(200, body, content_type or "application/octet-stream", headers)


def _body(request: Request) -> dict | None:
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
