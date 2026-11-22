"""Second-opinion dictionaries: a larger British word list, and macOS's own.

aspell's en_GB dictionary is small, so good British words crowd the likely
typos. A word aspell rejects but either of these knows is moved to its own
group, unless its reason is a strong one (a missing apostrophe, say).
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from texcheck import dictionaries

SCOWL = """Custom wordlist generated from https://app.aspell.net/create using
the English Speller Database

Copyright 2000-2026 by Kevin Atkinson

---
A
colour
heathland
accoutrement
"""


def test_words_from_scowl_skip_the_header():
    assert dictionaries.words_from(SCOWL) == ["A", "colour", "heathland", "accoutrement"]


def test_update_saves_the_list(tmp_path):
    target = tmp_path / "british.txt"
    count = dictionaries.update(target, fetch=lambda url: SCOWL.encode())
    assert count == 4
    assert dictionaries.load(target) == {"a", "colour", "heathland", "accoutrement"}


def test_missing_list_loads_as_none(tmp_path):
    assert dictionaries.load(tmp_path / "absent.txt") is None


def test_macos_answers_are_parsed():
    def fake(cmd, **kwargs):
        assert cmd[0] == "osascript"
        assert "laundrette" in cmd and "lyrca" in cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="laundrette\n", stderr="")
    assert dictionaries.ask_macos(["laundrette", "lyrca"], run=fake, platform="darwin") == {"laundrette"}


def test_macos_failure_or_other_systems_give_nothing():
    def broken(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)
    assert dictionaries.ask_macos(["laundrette"], run=broken, platform="darwin") == set()
    assert dictionaries.ask_macos(["laundrette"], platform="linux") == set()
    assert dictionaries.ask_macos([], platform="darwin") == set()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_real_macos_is_british():
    known = dictionaries.ask_macos(["colour", "color", "laundrette", "lyrca"], run=subprocess.run)
    assert known == {"colour", "laundrette"}


def test_notes_say_which_knew_it():
    notes = dictionaries.second_opinions(
        ["heathland", "laundrette", "telepaths", "lyrca"],
        british={"heathland", "telepaths"}, macos={"laundrette", "telepaths"},
    )
    assert notes == {
        "heathland": "in the larger British list",
        "laundrette": "known to macOS",
        "telepaths": "in the larger British list and known to macOS",
    }
