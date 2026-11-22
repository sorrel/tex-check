"""Keep tests independent of this machine's second-opinion dictionaries.

Without this, what macOS has "learned" and whether the larger British list
has been downloaded would change which group a word lands in. Tests that
want a second opinion patch `dictionaries.ask_macos` or `load` themselves.
"""

from __future__ import annotations

import pytest

from texcheck import dictionaries


@pytest.fixture(autouse=True)
def _no_second_opinions(request, monkeypatch):
    if request.node.module.__name__.endswith("test_dictionaries"):
        return
    monkeypatch.setattr(dictionaries, "ask_macos", lambda words, **kw: set())
    monkeypatch.setattr(dictionaries, "load", lambda path=None: None)
