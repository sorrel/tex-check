"""The terminal report: grouped, with locations short enough to read."""

import os
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


@needs_aspell
def test_long_paths_put_context_at_a_fixed_indent(checked, capsys, monkeypatch):
    """With a ~70-column absolute path the context must not be pushed off the line."""
    run, groups = checked
    monkeypatch.setattr(shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 40)))
    print_report(run, groups, Style(colour=False), cwd=Path("/nowhere/at/all"))
    lines = capsys.readouterr().out.splitlines()
    context = [line for line in lines if "in lyrca and" in line]
    assert context and all(line.startswith("    ") and not line.startswith("     ") for line in context)
    assert all(len(line) <= 100 for line in context)


@needs_aspell
def test_report_says_how_many_ok(checked, tmp_path, capsys):
    from texcheck.run import context_of
    run, groups = checked
    use = next(i for g in groups for i in g.items if i.word == "lyrca").uses[0]
    marked = group_findings(run, ok={("spelling", use.text, context_of(run.source, use))})
    print_report(run, marked, Style(colour=False), cwd=tmp_path)
    assert "1 marked OK" in capsys.readouterr().out


@needs_aspell
def test_top_suggestion_says_how_it_differs(checked, tmp_path, capsys):
    run, groups = checked
    print_report(run, groups, Style(colour=False), cwd=tmp_path)
    assert "Lycra (r and c swapped, capital L)" in capsys.readouterr().out


def test_changed_letters_are_underlined():
    from texcheck.report import underline_changes
    shown = underline_changes("Eclesall", "Ecclesall", Style(colour=True))
    assert shown == "E\033[4;1mc\033[0mclesall"


def test_tip_to_download_the_larger_list(capsys):
    from texcheck.report import print_spelling_note
    print_spelling_note({"gazetteer": True, "british": False}, Style(colour=False))
    assert "tex-check --update-dictionary" in capsys.readouterr().out
    print_spelling_note({"gazetteer": True, "british": True}, Style(colour=False))
    assert "update-dictionary" not in capsys.readouterr().out


def test_update_dictionary_command(monkeypatch, tmp_path, capsys):
    from texcheck import dictionaries
    from texcheck.cli import main
    monkeypatch.setattr(dictionaries, "update", lambda: 166_000)
    assert main(["--update-dictionary"]) == 0
    assert "166,000" in capsys.readouterr().out


def test_no_macos_flag_reaches_the_options(monkeypatch, tmp_path):
    from texcheck import cli
    tex = tmp_path / "doc.tex"
    tex.write_text("Hello.\n")
    seen = []

    def fake_check(path, stages, options, gazetteer, **kwargs):
        seen.append(options)
        raise SystemExit(0)

    monkeypatch.setattr(cli, "check_file", fake_check)
    with pytest.raises(SystemExit):
        cli.main([str(tex), "--no-macos", "--no-british"])
    assert (seen[0].macos, seen[0].british) == (False, False)


def test_layout_notes(capsys):
    from texcheck.report import print_layout_note
    print_layout_note({"stale": True, "unmatched": 3}, Style(colour=False))
    out = capsys.readouterr().out
    assert "older than the .tex" in out and "3 not matched" in out
