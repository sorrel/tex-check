"""The terminal report: grouped, with locations short enough to read."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from texcheck import wordlists
from texcheck.checks import STAGES
from texcheck.groups import group_findings
from texcheck.report import Style, as_json, display_path, print_report
from texcheck.run import Options, check_file

needs_aspell = pytest.mark.skipif(not shutil.which("aspell"), reason="aspell not installed")


def test_display_path_inside_cwd_is_relative(tmp_path):
    assert display_path(tmp_path / "a" / "doc.tex", tmp_path) == "a/doc.tex"


def test_display_path_outside_cwd_is_absolute(tmp_path):
    """Not ../../x: iTerm's Cmd-click resolves either, but absolute never misleads."""
    assert display_path(Path("/x/doc.tex"), tmp_path) == "/x/doc.tex"


@pytest.fixture
def checked(tmp_path, monkeypatch):
    monkeypatch.setattr(wordlists, "personal_file", lambda: tmp_path / "personal.txt")
    tex = tmp_path / "doc.tex"
    tex.write_text(
        "\\begin{document}\nWorking at Ericsson, in lyrca and lyrca.\n\\end{document}\n"
    )
    run = check_file(tex, STAGES, Options(), gazetteer=None)
    return run, group_findings(run)


@needs_aspell
def test_report_shows_groups_in_order_with_short_paths(checked, tmp_path, capsys):
    run, groups = checked
    print_report(run, groups, Style(colour=False), cwd=tmp_path)
    out = capsys.readouterr().out
    assert out.index("Likely typos") < out.index("Names")
    assert "doc.tex:2:" in out and str(tmp_path) + "/doc.tex:" not in out


@needs_aspell
def test_summary_lists_spelling_groups(checked, tmp_path, capsys):
    run, groups = checked
    print_report(run, groups, Style(colour=False), cwd=tmp_path)
    summary = capsys.readouterr().out.split("Summary")[1]
    assert "Likely typos" in summary and "Names" in summary


@needs_aspell
def test_json_has_group(checked):
    run, groups = checked
    spelling = [item for item in as_json(run, groups) if item["stage"] == "spelling"]
    assert {item["group"] for item in spelling} == {"typos", "names"}
    assert len(spelling) == 3  # every use, as before
