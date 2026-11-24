"""The browser view's defences, each tested against the attack it answers.

The page's buttons make the Mac type into Texifier and write word lists, and
every page in the browser can send requests to a port on loopback.
"""

from texcheck.web.security import (
    CSP,
    SECURITY_HEADERS,
    Request,
    TokenGate,
    check_request,
)

TOKEN = "a-very-secret-token"
PORT = 8766


def request(path="/api/findings", headers=None, query=None, header_token=True):
    base = {"Host": f"127.0.0.1:{PORT}"}
    if header_token:
        base["X-Tex-Check-Token"] = TOKEN
    base.update(headers or {})
    return Request(method="GET", path=path, query=query or {}, headers=base, body=b"")


def test_foreign_host_refused():
    refused = check_request(request(headers={"Host": f"evil.example:{PORT}"}), TokenGate(TOKEN), PORT)
    assert refused is not None and refused.status == 403


def test_api_needs_header_token():
    cookie_only = request(header_token=False, headers={"Cookie": f"tex_check_session={TOKEN}"})
    assert check_request(cookie_only, TokenGate(TOKEN), PORT).status == 403
    assert check_request(request(), TokenGate(TOKEN), PORT) is None


def test_cross_origin_refused():
    hostile = request(headers={"Origin": "http://evil.example"})
    assert check_request(hostile, TokenGate(TOKEN), PORT).status == 403


def test_cross_site_fetch_refused():
    hostile = request(headers={"Sec-Fetch-Site": "cross-site"})
    assert check_request(hostile, TokenGate(TOKEN), PORT).status == 403


def test_url_token_works_once():
    gate = TokenGate(TOKEN)
    page = request(path="/", query={"k": TOKEN}, header_token=False)
    assert check_request(page, gate, PORT) is None
    assert check_request(page, gate, PORT).status == 403


def test_page_reloads_with_the_cookie():
    page = request(path="/", header_token=False, headers={"Cookie": f"tex_check_session={TOKEN}"})
    assert check_request(page, TokenGate(TOKEN), PORT) is None


def test_nothing_may_frame_or_be_framed():
    assert "frame-src 'none'" in CSP
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"
