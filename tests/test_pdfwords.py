"""Reading word positions from the typeset PDF (macOS PDFKit)."""

from __future__ import annotations

import json
import subprocess

import pytest

from texcheck import pdfwords
from texcheck.pdfwords import Word, lines_of


def test_words_are_grouped_into_lines_by_position():
    words = [Word("one", 40, 60, 600), Word("two", 65, 80, 600.4), Word("three", 40, 70, 588),
             Word("four", 75, 95, 587.8)]
    assert [[w.text for w in line] for line in lines_of(words)] == [["one", "two"], ["three", "four"]]


def test_a_new_line_starts_when_the_text_goes_back_left():
    """Same height but back at the margin: the next line (a descender can shift y)."""
    words = [Word("a", 40, 50, 600), Word("b", 300, 310, 600), Word("c", 40, 50, 600)]
    assert len(lines_of(words)) == 2


def test_read_parses_and_caches(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    calls = []

    def fake(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps([[["Hello", 40, 60, 600]]]), "")

    first = pdfwords.read(pdf, cache=tmp_path / "cache", run=fake, platform="darwin")
    again = pdfwords.read(pdf, cache=tmp_path / "cache", run=fake, platform="darwin")
    assert first == again == [[Word("Hello", 40, 60, 600)]]
    assert len(calls) == 1


def test_read_fails_clearly_off_macos(tmp_path):
    with pytest.raises(pdfwords.Unreadable, match="macOS"):
        pdfwords.read(tmp_path / "doc.pdf", platform="linux")


def test_read_fails_clearly_when_pdfkit_does(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"x")

    def broken(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "cannot open")

    with pytest.raises(pdfwords.Unreadable):
        pdfwords.read(pdf, cache=tmp_path / "c", run=broken, platform="darwin")
