"""Keep tests independent of this machine's second-opinion dictionaries,
and of LanguageTool (which would start Java for every full check).

Without this, what macOS has "learned" and whether the larger British list
has been downloaded would change which group a word lands in. Tests that
want a second opinion patch `dictionaries.ask_macos` or `load` themselves.
"""

import pytest

from texcheck import dictionaries, languagetool


@pytest.fixture(autouse=True)
def _no_second_opinions(request, monkeypatch):
    if request.node.module.__name__.endswith("test_dictionaries"):
        return
    monkeypatch.setattr(dictionaries, "ask_macos", lambda words, **kw: set())
    monkeypatch.setattr(dictionaries, "load", lambda path=None: None)


@pytest.fixture(autouse=True)
def _no_languagetool(request, monkeypatch):
    if request.node.module.__name__.endswith("test_languagetool"):
        return

    def off():
        raise languagetool.Unavailable("off in tests")

    monkeypatch.setattr(languagetool, "server", off)
