"""Tense: a present-tense sentence alone in past-tense narration."""

import shutil

import pytest

from texcheck import languagetool as lt
from texcheck.checks import Settings, tense
from texcheck.latex import extract

# LanguageTool's tagger output (languagetool -t) for the texts below, trimmed
# to what tense.py reads: each word's readings and its chunk.
TAGS = {
    "slip": """\
<S> We[we/PRP,B-NP-singular] walked[walk/VBD,B-VP] down[down/IN,down/RB,down/VBP,B-ADVP] to[to/IN,to/TO,B-PP] the[the/DT,B-NP-singular] river[river/NN,E-NP-singular].[./.,</S>./PCT,O]
<S> The[the/DT,B-NP-singular] water[water/NN:U,E-NP-singular] is[be/VBZ,B-VP] cold[cold/JJ,B-ADJP] and[and/CC,O] he[he/PRP,B-NP-singular] jumps[jump/VBZ,B-VP] in[in/IN,in/RB,in/RP,B-PP].[./.,</S>./PCT,O]
<S> Then[then/RB,B-ADVP] we[we/PRP,B-NP-singular] went[go/VBD,B-VP] home[home/NN:UN,B-NP-singular].[./.,</S>./PCT,O]
""",
    "would": """\
<S> We[we/PRP,B-NP-singular] walked[walk/VBD,B-VP] home[home/NN,B-NP-singular].[./.,</S>./PCT,O]
<S> We[we/PRP,B-NP-singular] would[would/MD,B-VP] go[go/VB,go/VBP,B-VP] out[out/IN,out/RP,out/VBP,B-VP] and[and/CC,O] drink[drink/VB,drink/VBP,B-VP].[./.,</S>./PCT,O]
<S> Then[then/RB,B-ADVP] we[we/PRP,B-NP-singular] went[go/VBD,B-VP] home[home/NN:UN,B-NP-singular].[./.,</S>./PCT,O]
""",
    "dialogue": """\
<S> We[we/PRP,B-NP-singular] walked[walk/VBD,B-VP] home[home/NN,B-NP-singular].[./.,</S>./PCT,O]
<S> “[“/null,B-SBAR]It[it/PRP,B-NP-singular] is[be/VBZ,B-VP] cold[cold/JJ,B-ADJP]”[”/null,B-SBAR] she[she/PRP,B-NP-singular] said[say/VBD,say/VBN,B-VP].[./.,</S>./PCT,O]
<S> Then[then/RB,B-ADVP] we[we/PRP,B-NP-singular] went[go/VBD,B-VP] home[home/NN:UN,B-NP-singular].[./.,</S>./PCT,O]
""",
}

TEXTS = {
    "slip": "We walked down to the river. The water is cold and he jumps in. Then we went home.",
    "would": "We walked home. We would go out and drink. Then we went home.",
    "dialogue": "We walked home. “It is cold” she said. Then we went home.",
}


def body(text: str) -> str:
    return "\\begin{document}\n" + text + "\n\\end{document}\n"


@pytest.fixture
def tagged(monkeypatch):
    """Answer the tagger from TAGS, by which text it was given."""
    def tag(text: str) -> str:
        return next(TAGS[k] for k, t in TEXTS.items() if t in text)
    monkeypatch.setattr(tense, "_tag", tag)


def found(name: str) -> list[tuple[str, str]]:
    prose = extract(body(TEXTS[name]))
    return [(prose.text[f.start:f.end], f.message) for f in tense.run(prose, Settings())]


def test_a_present_sentence_between_past_ones(tagged):
    assert found("slip") == [("is", "present tense (“is”, “jumps”) between past-tense sentences")]


def test_would_and_could_are_past_narration(tagged):
    assert found("would") == []


def test_dialogue_is_left_alone(tagged):
    assert found("dialogue") == []


def test_tense_of_a_word():
    assert tense.tense_of("walked", "walk/VBD,B-VP") == "past"
    assert tense.tense_of("is", "be/VBZ,B-VP") == "present"
    assert tense.tense_of("Was", "be/VBD,O") == "past"           # inverted, outside a verb phrase
    assert tense.tense_of("out", "out/IN,out/RP,out/VBP,B-VP") is None  # a particle
    assert tense.tense_of("put", "put/VBD,put/VBN,put/VB,put/VBP,B-VP") is None  # either
    assert tense.tense_of("could", "can/MD,O") == "past"
    assert tense.tense_of("will", "will/MD,B-VP") == "present"
    assert tense.tense_of("should", "should/MD,B-VP") is None


def test_sentences_find_their_place_in_the_text():
    text = "We walked. He jumps."
    tags = ("<S> We[we/PRP,B-NP] walked[walk/VBD,B-VP].[./.,</S>./PCT,O]\n"
            "<S> He[he/PRP,B-NP] jumps[jump/VBZ,B-VP].[./.,</S>./PCT,O]\n")
    [first, second] = tense.sentences(text, tags)
    assert text[first.start:first.end] == "We walked."
    assert [(text[a:b], t) for a, b, t in second.verbs] == [("jumps", "present")]


@pytest.mark.skipif(not shutil.which("languagetool"), reason="LanguageTool not installed")
def test_the_real_tagger():
    assert "walk/VBD" in lt.tag("We walked home.")
