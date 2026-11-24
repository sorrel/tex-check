"""Every route, driven as a pure function. No socket, no browser, no Texifier."""

import json
import shutil

import pytest

from texcheck import wordlists
from texcheck.checks import STAGES
from texcheck.run import Options
from texcheck.web.routes import Router
from texcheck.web.security import Request
from texcheck.web.session import Session

pytestmark = pytest.mark.skipif(not shutil.which("aspell"), reason="aspell not installed")

TOKEN = "a-very-secret-token"
PORT = 8766


@pytest.fixture
def router(tmp_path, monkeypatch):
    monkeypatch.setattr(wordlists, "personal_file", lambda: tmp_path / "personal.txt")
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\nIn lyrca, in lyrca.\n\\end{document}\n")
    opened = []

    def opener(path, line, col, text=None):
        opened.append((line, col))
        return "Texifier is not installed" if line == 99 else None

    made = Router(Session(tex, STAGES, Options(), gazetteer=None, opener=opener), TOKEN, PORT)
    made.opened = opened
    return made


def call(router, path, method="GET", payload=None, token=True, query=None):
    headers = {"Host": f"127.0.0.1:{PORT}"}
    if token:
        headers["X-Tex-Check-Token"] = TOKEN
    body = json.dumps(payload).encode() if payload is not None else b""
    return router.handle(Request(method, path, query or {}, headers, body))


def first_use(router):
    findings = json.loads(call(router, "/api/findings").body)
    item = next(g for g in findings["groups"] if g["key"] == "typos")["items"][0]
    return item, item["uses"][0]


def test_index_embeds_token_and_sets_cookie(router):
    response = call(router, "/", token=False, query={"k": TOKEN})
    assert response.status == 200
    assert TOKEN.encode() in response.body
    assert "tex_check_session" in response.extra_headers["Set-Cookie"]


def asset(router, path):
    """Fetch as the browser does for a stylesheet: cookie, no header token."""
    headers = {"Host": f"127.0.0.1:{PORT}", "Cookie": f"tex_check_session={TOKEN}"}
    return router.handle(Request("GET", path, {}, headers, b""))


def test_static_refuses_traversal(router):
    assert asset(router, "/static/../routes.py").status == 404


def test_static_serves_the_stylesheet(router):
    response = asset(router, "/static/app.css")
    assert response.status == 200 and response.content_type == "text/css"


def test_open_calls_opener_with_line_and_col(router):
    _, use = first_use(router)
    response = call(router, "/api/open", "POST", {"use": use["id"]})
    assert json.loads(response.body) == {"ok": True}
    assert router.opened == [(use["line"], use["col"])]


def test_stale_id_is_refused(router):
    _, use = first_use(router)
    router.session.recheck()
    response = call(router, "/api/open", "POST", {"use": use["id"]})
    assert response.status == 409
    assert "reload" in json.loads(response.body)["error"]


def test_words_adds_and_reports_removed(router):
    item, _ = first_use(router)
    response = call(router, "/api/words", "POST", {"item": item["id"], "scope": "book"})
    assert json.loads(response.body) == {"removed": [item["id"]]}


def test_words_bad_scope_is_400(router):
    item, _ = first_use(router)
    response = call(router, "/api/words", "POST", {"item": item["id"], "scope": "nowhere"})
    assert response.status == 400


def test_malformed_body_is_400(router):
    response = router.handle(Request(
        "POST", "/api/open", {},
        {"Host": f"127.0.0.1:{PORT}", "X-Tex-Check-Token": TOKEN}, b"{not json"))
    assert response.status == 400


def test_status_reports_idle(router):
    assert json.loads(call(router, "/api/status").body)["state"] == "idle"


def test_api_without_token_is_403(router):
    assert call(router, "/api/findings", token=False).status == 403


def test_every_response_carries_security_headers(router):
    response = call(router, "/api/nothing-here")
    assert response.status == 404
    assert response.extra_headers["X-Frame-Options"] == "DENY"


def test_ok_route_hides_the_use(router):
    _, use = first_use(router)
    assert json.loads(call(router, "/api/ok", "POST", {"use": use["id"]}).body) == {"ok": True}
    item, still = first_use(router)
    assert still["id"] != use["id"]


def test_done_and_undo_routes(router):
    _, use = first_use(router)
    call(router, "/api/ok", "POST", {"use": use["id"]})
    [entry] = json.loads(call(router, "/api/done").body)["done"]
    assert entry["action"] == "ok"
    assert call(router, "/api/undo", "POST", {"entry": entry["id"]}).status == 200
    assert json.loads(call(router, "/api/done").body)["done"][0]["undone"] is True


def test_undo_unknown_is_404(router):
    assert call(router, "/api/undo", "POST", {"entry": "nope"}).status == 404
