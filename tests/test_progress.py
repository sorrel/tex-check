"""The status line shown on the terminal while a slow step runs."""

import io
import json
import subprocess

from texcheck import pdfwords
from texcheck.checks import resolve
from texcheck.progress import Progress
from texcheck.run import Options, check_file


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def progress(clock, enabled=True):
    stream = io.StringIO()
    return Progress(stream, enabled=enabled, clock=clock, threaded=False), stream


def test_nothing_is_shown_for_a_quick_step():
    clock = Clock()
    p, stream = progress(clock)
    p.say("Spelling")
    clock.now += 0.5
    p.draw()
    assert stream.getvalue() == ""


def test_a_slow_step_shows_what_it_is_doing_and_for_how_long():
    clock = Clock()
    p, stream = progress(clock)
    p.say("Layout: reading the PDF")
    clock.now += 12.3
    p.draw()
    assert "Layout: reading the PDF" in stream.getvalue()
    assert "12 s" in stream.getvalue()


def test_the_line_is_wiped_when_done():
    clock = Clock()
    p, stream = progress(clock)
    p.say("Spelling")
    clock.now += 5
    p.draw()
    p.close()
    assert stream.getvalue().endswith("\r\033[K")


def test_nothing_at_all_when_not_a_terminal():
    clock = Clock()
    p, stream = progress(clock, enabled=False)
    p.say("Spelling")
    clock.now += 60
    p.draw()
    p.close()
    assert stream.getvalue() == ""


def test_check_file_says_each_stage_as_it_starts(tmp_path):
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\nIt was the the end.\n\\end{document}\n")
    said = []
    check_file(tex, resolve(["repeats", "grammar"]), Options(), None, progress=said.append)
    assert said[-2:] == ["Repeated words", "Grammar (rule-based)"]


def test_reading_a_pdf_says_so_only_when_it_is_not_cached(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    def fake(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, json.dumps([[["Hello", 40, 60, 600]]]), "")

    said = []
    pdfwords.read(pdf, cache=tmp_path / "cache", run=fake, platform="darwin", say=said.append)
    pdfwords.read(pdf, cache=tmp_path / "cache", run=fake, platform="darwin", say=said.append)
    assert len(said) == 1 and "doc.pdf" in said[0]
