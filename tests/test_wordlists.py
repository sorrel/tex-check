"""The two word lists: one beside each book, one personal list for everything."""

import json
import shutil
from pathlib import Path

import pytest

from texcheck import wordlists
from texcheck.cli import main
from texcheck.wordlists import HEADER, append_word, load, personal_file

REPO = Path(__file__).resolve().parents[1]


def test_append_word_creates_with_header(tmp_path):
    target = tmp_path / "sub" / "w.txt"
    assert append_word(target, "Sohlberg") is True
    assert target.read_text().splitlines() == [HEADER, "Sohlberg"]


def test_append_word_normalises_and_dedupes(tmp_path):
    target = tmp_path / "w.txt"
    append_word(target, "Sohlberg’s")
    assert append_word(target, "sohlberg's") is False
    assert load([target]) == {"sohlberg's"}


def test_append_word_adds_a_missing_final_newline(tmp_path):
    """A list edited by hand may end without one; the new word must not join the last."""
    target = tmp_path / "w.txt"
    target.write_text("Ericsson")
    append_word(target, "Marmite")
    assert load([target]) == {"ericsson", "marmite"}


def test_load_skips_missing_files(tmp_path):
    assert load([tmp_path / "absent.txt"]) == set()


def test_personal_file_is_in_the_repo():
    assert personal_file() == REPO / "words.txt"


@pytest.mark.skipif(not shutil.which("aspell"), reason="aspell not installed")
def test_cli_reads_personal_list(tmp_path, monkeypatch, capsys):
    personal = tmp_path / "personal.txt"
    personal.write_text("lyrca\n")
    monkeypatch.setattr(wordlists, "personal_file", lambda: personal)
    tex = tmp_path / "book" / "doc.tex"
    tex.parent.mkdir()
    tex.write_text("\\begin{document}\nIn lyrca.\n\\end{document}\n")

    assert main([str(tex), "--only", "spell", "--json"]) == 0
    capsys.readouterr()
    assert main([str(tex), "--only", "spell", "--json", "--no-personal-words"]) == 1
    assert [item["text"] for item in json.loads(capsys.readouterr().out)] == ["lyrca"]
