"""The socket half: a real server on a port the kernel chooses."""

from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from urllib.parse import urlsplit

import pytest

from texcheck import wordlists
from texcheck.checks import STAGES
from texcheck.cli import main
from texcheck.run import Options
from texcheck.web.routes import Router
from texcheck.web.server import serve
from texcheck.web.session import Session

pytestmark = pytest.mark.skipif(not shutil.which("aspell"), reason="aspell not installed")


def test_server_answers_on_loopback(tmp_path, monkeypatch):
    monkeypatch.setattr(wordlists, "personal_file", lambda: tmp_path / "personal.txt")
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\nIn lyrca.\n\\end{document}\n")
    session = Session(tex, STAGES, Options(), gazetteer=None)
    router = Router(session, "a-token", port=0)
    ready = threading.Event()
    found: dict = {}

    def on_ready(url, port, stop):
        found.update(url=url, port=port, stop=stop)
        ready.set()

    thread = threading.Thread(
        target=serve, args=(router,), kwargs={"port": 0, "open_browser": False, "on_ready": on_ready},
        daemon=True,
    )
    thread.start()
    assert ready.wait(5)
    try:
        assert urlsplit(found["url"]).hostname == "127.0.0.1"
        with urllib.request.urlopen(found["url"], timeout=5) as page:
            assert page.status == 200 and b"<html" in page.read()
        api = urllib.request.Request(
            f"http://127.0.0.1:{found['port']}/api/findings",
            headers={"X-Tex-Check-Token": "a-token"},
        )
        with urllib.request.urlopen(api, timeout=5) as reply:
            assert json.loads(reply.read())["version"] == 1
    finally:
        found["stop"]()
        thread.join(5)
    assert not thread.is_alive()


def test_web_takes_one_file(tmp_path, capsys):
    one, two = tmp_path / "a.tex", tmp_path / "b.tex"
    one.write_text("x")
    two.write_text("y")
    assert main([str(one), str(two), "--web"]) == 2
    assert "--web takes one file" in capsys.readouterr().err


@pytest.mark.parametrize("typed", ["q\n", "quit\n", "EXIT\n", "  q  \n"])
def test_typing_quit_stops_the_server(typed):
    import io

    from texcheck.web.server import listen_for_quit
    stopped = []
    listen_for_quit(io.StringIO("hello\n" + typed + "more\n"), lambda: stopped.append(True))
    assert stopped == [True]


def test_other_input_does_not_stop_it():
    import io

    from texcheck.web.server import listen_for_quit
    stopped = []
    listen_for_quit(io.StringIO("query\nquite\n\n"), lambda: stopped.append(True))
    assert stopped == []
