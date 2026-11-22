"""Sorting findings into groups, so the likely mistakes come first."""

from __future__ import annotations

import shutil

import pytest

from texcheck import wordlists
from texcheck.checks import STAGES
from texcheck.groups import group_findings
from texcheck.run import Options, check_file

pytestmark = pytest.mark.skipif(not shutil.which("aspell"), reason="aspell not installed")


@pytest.fixture
def groups_of(tmp_path, monkeypatch):
    """Check a fragment of prose and return its groups, keyed by group key.

    The personal list is pointed at an empty file so the repository's own
    words.txt cannot change what these tests see.
    """
    monkeypatch.setattr(wordlists, "personal_file", lambda: tmp_path / "personal.txt")

    def run(text: str) -> dict:
        tex = tmp_path / "doc.tex"
        tex.write_text("\\begin{document}\n" + text + "\n\\end{document}\n")
        groups = group_findings(check_file(tex, STAGES, Options(), gazetteer=None))
        return {group.key: group for group in groups}

    return run


def words_in(groups: dict, key: str) -> list[str]:
    return [item.word for item in groups[key].items] if key in groups else []


def test_macro_slip_is_a_typo(groups_of):
    groups = groups_of(r"She was briefly bsq{entertainment} for Byron.")
    assert words_in(groups, "typos") == ["bsqentertainment"]
    assert "\\bsq" in groups["typos"].items[0].note


def test_case_only_difference_is_a_variant(groups_of):
    assert words_in(groups_of("And it had been ok, so I went."), "variants") == ["ok"]


def test_split_word_is_a_variant(groups_of):
    assert words_in(groups_of("Back to the heathland in winter."), "variants") == ["heathland"]


def test_dialogue_goes_to_quotes(groups_of):
    assert "vos" in words_in(groups_of(r"\say{That vos a pity} said the man."), "quotes")


def test_bold_foreign_phrase(groups_of):
    groups = groups_of(r"Then shouting \textbf{au secours} again.")
    assert "secours" in words_in(groups, "bold")


def test_mid_sentence_capital_is_a_name(groups_of):
    assert words_in(groups_of("When working at Ericsson, we met."), "names") == ["Ericsson"]


def test_sentence_initial_capital_is_not_a_name(groups_of):
    groups = groups_of("Lineker scored in the second half.")
    assert words_in(groups, "names") == []
    assert words_in(groups, "other") == ["Lineker"]


def test_lowercase_with_suggestions_is_a_typo(groups_of):
    assert words_in(groups_of("Dressed up in capes, in lyrca? No."), "typos") == ["lyrca"]


def test_word_uses_are_one_item(groups_of):
    item = groups_of("A lyrca here. Then lyrca there.")["typos"].items[0]
    assert len(item.uses) == 2


def test_display_order(groups_of):
    groups = groups_of(
        "It was was fine.  Then lyrca. Lineker ran. it was ok. "
        r"\say{That vos a pity}. \textbf{au secours} at Ericsson and the heathland."
    )
    assert list(groups) == [
        "repeats", "punctuation", "typos", "other", "quotes", "bold", "names",
        "variants", "grammar",
    ]


def test_empty_spelling_is_one_group(groups_of):
    groups = groups_of("All is well.")
    assert "spelling" in groups and groups["spelling"].items == []
