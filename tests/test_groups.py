"""Sorting findings into groups, so the likely mistakes come first."""

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


def test_macro_slip_is_wrong_latex_not_a_typo(groups_of):
    groups = groups_of(r"She was briefly bsq{entertainment} for Byron.")
    assert words_in(groups, "latex") == ["bsqentertainment"]
    assert words_in(groups, "typos") == []
    assert "\\bsq" in groups["latex"].items[0].note


def test_macro_slip_suggests_the_command_not_a_word(groups_of):
    """aspell's nearest word ("discontentment") is no help: the fix is the backslash.
    Nor is adding "bsqentertainment" to a word list."""
    [item] = groups_of(r"She was briefly bsq{entertainment} for Byron.")["latex"].items
    assert item.suggestions == ["\\bsq{entertainment}"]
    assert not item.addable


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
    """The spec: likely typos are lower-case-initial *or sentence-initial*."""
    groups = groups_of("It rained. Recieve the post.")
    assert words_in(groups, "names") == []
    assert words_in(groups, "typos") == ["Recieve"]


def test_quoted_contraction_stays_a_quotation(groups_of):
    assert "vould" in words_in(groups_of("He said \\bsq{there’d vould be none} then."), "quotes")


def test_lowercase_with_suggestions_is_a_typo(groups_of):
    assert words_in(groups_of("Dressed up in capes, in lyrca? No."), "typos") == ["lyrca"]


def test_word_uses_are_one_item(groups_of):
    item = groups_of("A lyrca here. Then lyrca there.")["typos"].items[0]
    assert len(item.uses) == 2


def test_display_order(groups_of):
    groups = groups_of(
        "It was was fine.  Then lyrca. it was ok. "
        r"\say{That vos a pity}. \textbf{au secours} at Ericsson and the heathland."
    )
    assert list(groups) == [
        # "other" is left with only words aspell cannot suggest anything for,
        # which it nearly always can; empty groups are not shown.
        "repeats", "near-repeats", "punctuation", "typos", "quotes", "bold", "names",
        "variants", "grammar", "languagetool", "layout",
    ]


def test_empty_spelling_is_one_group(groups_of):
    groups = groups_of("All is well.")
    assert "spelling" in groups and groups["spelling"].items == []


# ── reasons ─────────────────────────────────────────────────────────────────

from texcheck.groups import reason


@pytest.mark.parametrize(("word", "suggestions", "expected"), [
    ("Ziggys", ["Ziggy's", "Ziggy", "Piggy's"], "missing apostrophe?"),
    ("ok", ["OK", "OJ"], "capitals differ"),
    ("heathland", ["heath land", "heath-land"], "usually two words"),
    ("seatbelts", ["seat belts", "seat-belts"], "usually two words"),
    ("ensuite", ["en suite", "en-suite"], "usually two words"),
    ("ouija", ["Ouija"], "capitals differ"),
    ("lyrca", ["Lycra", "Lyra"], "not in the dictionary"),
    ("dénouement", ["denouement"], "accent differs"),
    ("practiced", ["practices", "practice", "practised"], "American spelling?"),
    ("advisors", ["advisers", "advises"], "not in the dictionary"),
    ("colorful", ["colourful"], "American spelling?"),
    ("realize", ["realise"], "American spelling?"),
    ("center", ["centre"], "American spelling?"),
    ("accoutrement", ["accoutrements", "acquirement"], "aspell knows only the plural"),
    ("synthesisers", ["synthesises", "synthesizers"], "British spelling; aspell knows only the American"),
    ("technicolour", ["Technicolor", "technicolor"], "British spelling; aspell knows only the American"),
])
def test_reasons(word, suggestions, expected):
    assert reason(word, suggestions, "") == expected


def test_hyphenated_reason_follows_the_first_matching_suggestion():
    assert reason("cooperate", ["co-operate", "co operate"], "") == "usually hyphenated"


def test_macro_slip_reason_is_its_note():
    assert reason("bsqentertainment", [], "missing \\ before \\bsq?") == "missing \\ before \\bsq?"


def test_items_carry_their_reason(groups_of):
    item = groups_of("Dressed up in capes, in lyrca? No.")["typos"].items[0]
    assert item.reason == "not in the dictionary"


# ── OK marks ────────────────────────────────────────────────────────────────

from texcheck.run import context_of


def _check(tmp_path, monkeypatch, text, mark=None):
    """Check `text`; with `mark` (a word), first mark its first use OK."""
    monkeypatch.setattr(wordlists, "personal_file", lambda: tmp_path / "personal.txt")
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\n" + text + "\n\\end{document}\n")
    run = check_file(tex, STAGES, Options(), gazetteer=None)
    ok = set()
    if mark:
        use = next(i for g in group_findings(run) for i in g.items if i.word == mark).uses[0]
        ok = {("spelling", use.text, context_of(run.source, use))}
    return {g.key: g for g in group_findings(run, ok=ok)}


def test_ok_mark_hides_one_use(tmp_path, monkeypatch):
    groups = _check(tmp_path, monkeypatch, "A lyrca here.\n\nThen lyrca there.", mark="lyrca")
    [item] = groups["typos"].items
    assert len(item.uses) == 1 and item.uses[0].line == 4
    assert groups["typos"].hidden == 1


def test_all_uses_ok_removes_the_item(tmp_path, monkeypatch):
    groups = _check(tmp_path, monkeypatch, "Only one lyrca here.", mark="lyrca")
    assert groups["typos"].items == [] and groups["typos"].hidden == 1


def test_two_uses_on_one_short_line_are_two_places(tmp_path, monkeypatch):
    groups = _check(tmp_path, monkeypatch, "A lyrca, a lyrca.", mark="lyrca")
    assert len(groups["typos"].items[0].uses) == 1


def test_words_another_dictionary_knows_get_their_own_group(groups_of, monkeypatch):
    from texcheck import dictionaries
    monkeypatch.setattr(dictionaries, "ask_macos", lambda words, **kw: {"laundrette", "Ziggys", "practiced"})
    groups = groups_of("We went to the laundrette, which Ziggys practiced in, and a lyrca.")
    assert words_in(groups, "elsewhere") == ["laundrette"]
    assert groups["elsewhere"].items[0].reason == "only this Mac knows it"
    # Strong reasons win over another dictionary's say-so.
    assert "Ziggys" in words_in(groups, "names")
    assert "practiced" in words_in(groups, "typos")
    assert "lyrca" in words_in(groups, "typos")


def test_probably_correct_comes_after_every_stage(tmp_path, monkeypatch):
    from texcheck import dictionaries
    monkeypatch.setattr(wordlists, "personal_file", lambda: tmp_path / "personal.txt")
    monkeypatch.setattr(dictionaries, "ask_macos", lambda words, **kw: {"laundrette"})
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\nThe the laundrette, and a lyrca.\n\\end{document}\n")
    keys = [g.key for g in group_findings(check_file(tex, STAGES, Options(), gazetteer=None))]
    assert keys[-1] == "elsewhere"
    assert keys.count("elsewhere") == 1


def test_spelling_keeps_its_place_when_every_word_is_probably_correct(tmp_path, monkeypatch):
    from texcheck import dictionaries
    monkeypatch.setattr(wordlists, "personal_file", lambda: tmp_path / "personal.txt")
    monkeypatch.setattr(dictionaries, "ask_macos", lambda words, **kw: {"laundrette"})
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\nWe went to the laundrette.\n\\end{document}\n")
    run = check_file(tex, STAGES, Options(), gazetteer=None)
    keys = [g.key for g in group_findings(run)]
    stages = [stage.NAME for stage, _ in run.results]
    assert keys[-1] == "elsewhere"
    assert keys.index("spelling") == stages.index("spelling")


def test_a_word_in_the_british_list_gets_no_note(groups_of, monkeypatch):
    from texcheck import dictionaries
    monkeypatch.setattr(dictionaries, "load", lambda path=None: {"laundrette"})
    monkeypatch.setattr(dictionaries, "ask_macos", lambda words, **kw: {"laundrette"})
    [item] = groups_of("We went to the laundrette.")["elsewhere"].items
    assert item.note == "" and item.reason == ""
