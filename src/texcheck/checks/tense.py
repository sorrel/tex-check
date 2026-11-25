"""Stage 7: tense, a present-tense sentence alone in past-tense narration.

"We walked down to the river. The water is cold and he jumps in. Then we
went home." The middle sentence slips into the present. A sentence is
past, present, mixed or neither by its finite verbs, outside dialogue
(“…”); one that is present, with a past one before and after it in the
same paragraph, is reported. A run of present sentences is left alone: it
is more likely a deliberate aside ("Children are uninterested in things
that matter to their parents.") than a slip. Many reports will still be
deliberate: they are prompts to look.

The verbs come from LanguageTool's tagger (languagetool.tag), run on this
Mac. Only the word that starts a verb phrase counts ("would go": would),
except be, have and do, which the chunker leaves out of inverted questions
("Was she…"). "Would", "could", "might" and "'d" count as past: they are
how past narration speaks of habit and possibility. A word after "to" is
an infinitive; a capitalised word mid-sentence is a name ("Rolls"); one
that can be a preposition or particle ("out", "down") is not counted.

Tried on two books (25 November 2026): 17 and 11 reports, most of them
real present-tense asides; the rest are words LanguageTool misreads as
verbs ("rain drops arrived").
"""

import re
from bisect import bisect_right
from dataclasses import dataclass, field

from .. import languagetool
from ..findings import Finding, Skipped
from ..prose import BREAK

NAME = "tense"
TITLE = "Tense"
BLURB = "a present-tense sentence in past-tense narration"

PAST_MODALS = {"would", "could", "might", "'d", "’d"}
PRESENT_MODALS = {"will", "can", "may", "shall", "'ll", "’ll", "wo", "ca"}
_SENTENCE = re.compile(r"<S>(.*?)</S>")
_WORD = re.compile(r"(\S+?)\[([^\]]*)\]")
_DIALOGUE = re.compile(r"“[^”\n]*”")


@dataclass
class Sentence:
    start: int
    end: int
    verbs: list[tuple[int, int, str]] = field(default_factory=list)  # (start, end, tense)

    @property
    def tense(self) -> str:
        tenses = {t for _, _, t in self.verbs}
        return tenses.pop() if len(tenses) == 1 else ("mixed" if tenses else "none")


def tense_of(word: str, readings: str) -> str | None:
    """"past", "present" or None, for one tagged word (`lemma/TAG,...,chunk`)."""
    parts = readings.split(",")
    chunk = parts[-1]
    pairs = [p.rsplit("/", 1) for p in parts[:-1] if "/" in p]
    tags = {t for _, t in pairs}
    lemmas = {lemma for lemma, _ in pairs}
    lower = word.lower()
    if lower in PAST_MODALS:
        return "past"
    if "MD" in tags:
        return "present" if lower in PRESENT_MODALS else None
    if not (chunk.startswith("B-VP") or lemmas & {"be", "have", "do"}):
        return None
    if tags & {"IN", "RP", "UH"}:
        return None
    past, present = "VBD" in tags, bool(tags & {"VBZ", "VBP"})
    if past != present:
        return "past" if past else "present"
    return None


def sentences(text: str, tags: str) -> list[Sentence]:
    """The tagger's sentences placed in `text`, each with its finite verbs."""
    out: list[Sentence] = []
    cursor = 0
    for line in _SENTENCE.finditer(tags):
        sentence, previous, first = None, "", True
        for word, readings in _WORD.findall(line.group(1) + "]"):
            at = text.find(word, cursor)
            if at < 0 or at - cursor > 200:   # the tagger's own token: not in the text
                continue
            cursor = at + len(word)
            if sentence is None:
                sentence = Sentence(at, cursor)
            sentence.end = cursor
            name = word[:1].isupper() and not first and word != "I"
            if previous.lower() != "to" and not name and (t := tense_of(word, readings)):
                sentence.verbs.append((at, cursor, t))
            if word.strip("“‘(—-"):
                first = False
            previous = word
        if sentence is not None:
            out.append(sentence)
    return out


def run(prose, settings) -> list[Finding]:
    text = prose.text
    settings.progress("Tense: LanguageTool is reading the verbs")
    try:
        tags = _tag(text)
    except languagetool.Unavailable as err:
        raise Skipped(str(err)) from err
    dialogue = [m.span() for m in _DIALOGUE.finditer(text)]
    starts = [a for a, _ in dialogue]

    def spoken(at: int) -> bool:
        k = bisect_right(starts, at) - 1
        return k >= 0 and dialogue[k][0] <= at < dialogue[k][1]

    found = []
    for paragraph in _paragraphs(text, sentences(text, tags)):
        for s in paragraph:
            s.verbs = [v for v in s.verbs if not spoken(v[0]) and not prose.bold[v[0]]]
        for before, s, after in zip(paragraph, paragraph[1:], paragraph[2:], strict=False):
            if s.tense == "present" and before.tense == "past" and after.tense == "past":
                verbs = ", ".join(f"“{text[a:b]}”" for a, b, _ in s.verbs)
                a, b, _ = s.verbs[0]
                found.append(Finding(NAME, a, b,
                                     f"present tense ({verbs}) between past-tense sentences"))
    return found


def _tag(text: str) -> str:
    return languagetool.tag(text)


def _paragraphs(text: str, found: list[Sentence]) -> list[list[Sentence]]:
    """Sentences grouped by paragraph: a blank line between two splits them."""
    out: list[list[Sentence]] = []
    for s in found:
        if out and BREAK not in text[out[-1][-1].end:s.start]:
            out[-1].append(s)
        else:
            out.append([s])
    return out
