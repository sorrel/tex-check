import shutil

import pytest

from texcheck.checks import Settings, grammar, punctuation, repeats, resolve, spelling
from texcheck.cli import main
from texcheck.latex import extract
from texcheck.prose import Source


def body(text: str) -> str:
    return "\\documentclass{article}\n\\usepackage{x}\n\\begin{document}\n" + text + "\n\\end{document}\n"


def messages(stage, tex, **settings):
    prose = extract(body(tex))
    return [f.message for f in stage.run(prose, Settings(**settings))]


# ── extraction ──────────────────────────────────────────────────────────────

def test_preamble_and_commands_are_not_prose():
    prose = extract(body(r"\noindent Hello \textbf{world}.\label{x} % hidden"))
    assert prose.text.strip() == "Hello world."


def test_offsets_point_back_into_the_source():
    src = body(r"Word \textbf{the} end")
    prose = extract(src)
    k = prose.text.index("the")
    start, end = prose.source_span(k, k + 3)
    assert src[start:end] == "the"
    assert Source(src).line_col(start) == (4, 14)


def test_footnotes_are_lifted_out():
    prose = extract(body(r"It was seen\footnote{A note here.}. Then more."))
    assert "It was seen. Then more." in prose.text
    assert "A note here." in prose.text


def test_line_breaks_and_quotes():
    prose = extract(body(r"\begin{words}{\say{Oranges}\\say the bells}\end{words} \bsq{p}"))
    assert "“Oranges”" in prose.text and "say the bells" in prose.text
    assert "‘p’" in prose.text
    assert "”\n\nsay" in prose.text


def test_maths_and_verbatim_are_skipped():
    prose = extract(body("Cost $x^2$ pounds.\n\\begin{verbatim}teh teh\\end{verbatim}"))
    assert "teh" not in prose.text
    assert "Cost 0 pounds." in prose.text


def test_dropped_arguments():
    prose = extract(body(r"A\vspace{3pt} B\setcounter{page}{2} C \href{http://x}{link}"))
    assert prose.text.split() == ["A", "B", "C", "link"]


def test_horizontal_space_separates_words():
    prose = extract(body(r"fingers slip\hspace{39pt}between\hspace*{10pt}desire\quad end"))
    assert prose.text.split() == ["fingers", "slip", "between", "desire", "end"]


def test_space_before_horizontal_space_is_not_a_double_space():
    tex = r"the edge of sight \hspace{17pt}and layered sweat \quad on, but  here"
    assert messages(punctuation, tex) == ["double space"]


def test_contents_lines_are_not_prose():
    prose = extract(body(
        r"\addcontentsline{toc}{chapter}{\protect\numberline{}Poems for Children}"
        r"\addtocontents{toc}{\protect\vspace{4pt}}Text."))
    assert prose.text.strip() == "Text."


# ── stages ─────────────────────────────────────────────────────────────────

def test_repeats_across_markup_and_lines():
    assert messages(repeats, "in the \\textbf{the} end") == ["“the the”"]
    assert messages(repeats, "in the\nthe end") == ["“the the”"]


def test_repeats_not_across_punctuation_or_lyric_lines():
    assert messages(repeats, "no, no") == []
    assert messages(repeats, "baby\\\\baby") == []


def test_punctuation():
    found = messages(punctuation, "One  two , three,, four.. five,six (seven )")
    assert "double space" in found
    assert "space before punctuation" in found
    assert "doubled punctuation" in found
    assert "two full stops (one, or an ellipsis?)" in found
    assert "no space after punctuation" in found
    assert "space before closing bracket" in found


def test_words_run_together_after_markup():
    found = messages(punctuation, r"written by\textbf{The Author}")
    assert found == ["words run together (missing space?)"]


def test_punctuation_leaves_good_text_alone():
    assert messages(punctuation, "Well... fine, etc., and (yes) 1,000 St. Bedes.") == []


def test_double_space_from_removed_command_is_ignored():
    assert messages(punctuation, "one \\label{x} two") == []


def test_unbalanced_brackets():
    assert messages(punctuation, "a (b c") == ["unclosed “(”"]


def test_grammar():
    found = " | ".join(messages(grammar, "A apple could of been more then its a i think. then her's"))
    for bit in ("should it be “an”", "“could of”", "“than”", "“it's”", "lower-case “i”", "capital", "“hers”"):
        assert bit in found


def test_grammar_exceptions():
    assert messages(grammar, "A unicorn, an hour, an LP, a one-off, etc. and so on.") == []


@pytest.mark.skipif(not shutil.which("aspell"), reason="aspell not installed")
def test_spelling(tmp_path):
    words = tmp_path / "w.txt"
    words.write_text("Tobermory\n")
    tex = r"I recieve \textbf{Zorblax} at Tobermory and Qwzx."
    found = spelling.run(extract(body(tex)), Settings(wordlists=[words]))
    assert {f.group for f in found} == {"recieve", "Qwzx"}
    assert "receive" in next(f for f in found if f.group == "recieve").suggestions


needs_aspell = pytest.mark.skipif(not shutil.which("aspell"), reason="aspell not installed")


@needs_aspell
def test_urls_are_not_spell_checked():
    tex = r"Printed by them (https://youloveprint.co.uk) and see elmandash.co.uk today."
    assert messages(spelling, tex) == []


@needs_aspell
def test_words_beside_urls_still_are():
    assert messages(spelling, r"A lyrca at https://example.com/x.") == ["lyrca"]


def test_resolve_aliases_and_order():
    assert [s.NAME for s in resolve(["spell", "repeat"])] == ["repeats", "spelling"]
    with pytest.raises(ValueError):
        resolve(["nonsense"])


def test_cli_exit_codes(tmp_path, capsys):
    good, bad = tmp_path / "good.tex", tmp_path / "bad.tex"
    good.write_text(body("All is well."))
    bad.write_text(body("All is is well."))
    assert main([str(good), "--only", "repeats"]) == 0
    assert main([str(bad), "--only", "repeats", "--json"]) == 1
    assert '"line": 4' in capsys.readouterr().out


def test_bold_names_are_not_repeats():
    assert messages(repeats, r"by \textbf{Duran Duran} and \textbf{The The}") == []


# ── place names ────────────────────────────────────────────────────────────

GEONAMES_ROWS = (
    "1\tGrasmere\tGrasmere\t\t54.4\t-3.0\tP\tPPL\n"
    "2\tTurku\tTurku\tAbo,Åbo,Турку\t60.4\t22.2\tP\tPPLA\n"
    "3\tHer\tHer\t\t0\t0\tP\tPPL\n"
)


def test_gazetteer_tokens_keep_latin_alternates_only():
    from texcheck.places import tokens_from
    words = tokens_from(GEONAMES_ROWS, with_alternates=True)
    assert {"Grasmere", "Turku", "Abo", "Åbo", "Her"} <= words
    assert "Турку" not in words


def test_is_place_needs_a_capital_and_a_long_enough_possessive():
    from texcheck.places import is_place
    places = {"Grasmere", "Her"}
    assert is_place("Grasmere", places)
    assert is_place("Grasmere's", places)
    assert not is_place("grasmere", places)
    assert not is_place("Her's", places)


@pytest.mark.skipif(not shutil.which("aspell"), reason="aspell not installed")
def test_spelling_accepts_places_and_counts_them():
    settings = Settings(places={"Llanberis"})
    found = spelling.run(extract(body("From Llanberis I recieve post. llanberis")), settings)
    assert {f.group for f in found} == {"recieve", "llanberis"}
    assert settings.stats["spelling"]["places"] == 1


# ── hyphenated words ───────────────────────────────────────────────────────


def test_compounds_are_found_whole():
    text = "an absent-mindedly resigned, well-to-do man; mindedly"
    whole = [spelling.compound(text, text.index(part), text.index(part) + len(part))
             for part in ("mindedly", "to", "man")]
    assert whole == ["absent-mindedly", "well-to-do", None]


@needs_aspell
def test_a_fragment_passes_when_the_whole_word_is_known(monkeypatch):
    from texcheck import dictionaries
    monkeypatch.setattr(dictionaries, "load", lambda path=None: {"absentmindedly"})
    tex = r"\textbf{absent-mindedly resigned}, she said absent-mindedly; but mindedly alone."
    found = spelling.run(extract(body(tex)), Settings())
    assert [f.message for f in found] == ["mindedly"]
    assert found[0].start > extract(body(tex)).text.index("but")


@needs_aspell
def test_macos_and_word_lists_vouch_for_compounds(monkeypatch, tmp_path):
    from texcheck import dictionaries
    monkeypatch.setattr(dictionaries, "ask_macos",
                        lambda words, **kw: {w for w in words if w == "sixty-seater"})
    words = tmp_path / "w.txt"
    words.write_text("zorb-blaxing\n")
    tex = "a sixty-seater coach, zorb-blaxing all the way"
    assert messages(spelling, tex, wordlists=[words]) == []
