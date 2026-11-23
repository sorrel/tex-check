"""Layout findings sorted into groups, like spelling's."""

from __future__ import annotations

import pytest

from texcheck.checks import STAGES, layout
from texcheck.groups import group_findings
from texcheck.report import Style, print_report, print_summary
from texcheck.run import Options, check_file
from tests.test_layout import line, page

SRC = ("\\begin{document}\n"
       "The gate was shut and the dog was barking at the gate as if it knew we were there.\n\n"
       "We waited by the road until the rain stopped and then we went.\n"
       "\\end{document}\n")


@pytest.fixture
def run(tmp_path, monkeypatch):
    tex = tmp_path / "doc.tex"
    tex.write_text(SRC)
    (tmp_path / "doc.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(layout.pdfwords, "read", lambda pdf, **kw: [page(
        line(600, "The gate was shut and the dog was barking at the"),
        line(588, "gate as if it knew we were there.", full=False),
        line(576, "We waited by the road until the rain stopped and then we"),
        line(564, "went.", full=False),
    )])
    return check_file(tex, [layout], Options(), gazetteer=None)


def test_layout_is_split_into_groups_in_a_fixed_order(run):
    groups = [g for g in group_findings(run) if g.section == "Layout"]
    assert [(g.key, g.title, len(g.items)) for g in groups] == [
        ("layout-runt", "One-word last lines", 1),
    ]


def test_report_shows_layout_under_one_heading(run, tmp_path, capsys):
    groups = group_findings(run)
    print_report(run, groups, Style(colour=False), cwd=tmp_path)
    out = capsys.readouterr().out
    assert out.count("Layout") >= 2  # the heading and the summary
    assert "One-word last lines" in out
    assert "1 finding" in out


def test_summary_lists_layout_groups(run, capsys):
    print_summary(run, group_findings(run), Style(colour=False))
    out = capsys.readouterr().out
    assert "Layout" in out and "  One-word last lines" in out


def test_no_findings_keeps_one_layout_group(tmp_path, monkeypatch):
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\nHello there.\n\\end{document}\n")
    (tmp_path / "doc.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(layout.pdfwords, "read", lambda pdf, **kw: [page(line(600, "Hello there.", full=False))])
    groups = group_findings(check_file(tex, STAGES[-1:], Options(), gazetteer=None))
    assert [g.key for g in groups] == ["layout"]
