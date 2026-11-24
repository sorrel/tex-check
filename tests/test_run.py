"""One check run, shared by the terminal report, --json and the browser view."""

import shutil

import pytest

from texcheck import wordlists
from texcheck.checks import STAGES
from texcheck.run import Options, check_file

pytestmark = pytest.mark.skipif(not shutil.which("aspell"), reason="aspell not installed")


def outcome(run, name):
    return next(found for stage, found in run.results if name == stage.NAME)


def test_check_file_finds_and_rereads_word_lists(tmp_path, monkeypatch):
    monkeypatch.setattr(wordlists, "personal_file", lambda: tmp_path / "personal.txt")
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\nIt was the the lyrca.\n\\end{document}\n")

    first = check_file(tex, STAGES, Options(), gazetteer=None)
    assert len(outcome(first, "repeats")) == 1
    assert [f.group for f in outcome(first, "spelling")] == ["lyrca"]

    # The lists are read on every run, so a word added between runs counts.
    wordlists.book_file(tex).write_text("lyrca\n")
    second = check_file(tex, STAGES, Options(), gazetteer=None)
    assert outcome(second, "spelling") == []


def test_missing_aspell_is_a_skipped_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\nHello.\n\\end{document}\n")
    run = check_file(tex, STAGES, Options(), gazetteer=None)
    assert "aspell" in outcome(run, "spelling")
