"""Stage 3: spelling, using aspell's British English (-ise) dictionary.

Each distinct word is sent to aspell once, in pipe mode, and every
occurrence of an unknown word becomes a finding, grouped by word.

Left alone by default, to keep the list to likely mistakes:

* bold words that start with a capital (this house style bolds the names of
  bands, people and places); --spell-bold checks them too;
* ALL-CAPS words (acronyms such as INLA); --spell-capitals checks them;
* single letters and words containing digits;
* any word in a word list (see wordlists.py): the book's own, the personal
  list and any --words files;
* capitalised words that aspell does not know but the place-name gazetteer
  does (see places.py; built with `tex-check --update-places`).

Words aspell rejects are also put to two larger dictionaries (see
dictionaries.py). They are still findings; the note of which dictionary
knew each is left in the stats for `groups` to sort by.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from .. import dictionaries
from ..findings import Finding
from ..places import is_place
from ..wordlists import load as load_wordlists
from ..wordlists import normalise

NAME = "spelling"
TITLE = "Spelling"
BLURB = "aspell, British English"

WORD = re.compile(r"(?<!\d)[^\W\d_]+(?:['’][^\W\d_]+)*")  # not "th" in 13th

#: Web addresses are not prose: without this, `https`, `uk` and the run-together
#: domain names in a colophon each count as a misspelling. Bare domains are
#: matched only on the endings these books use, so "e.g." and "etc." are safe.
URL = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|uk|io|fi|de|fr|ie|eu)\b(?:/\S*)?"
)

# Good British English that aspell's en_GB dictionaries lack (checked against
# aspell 0.60.8, November 2026).
ALWAYS_ACCEPT = {
    "among", "learned", "spilled", "spelled", "dreamt", "leant", "kneeled",
    "focussed",
}


class SpellerMissing(RuntimeError):
    pass




def candidates(prose, settings):
    """Yield (match, normalised word) for each word occurrence worth checking."""
    text = prose.text
    urls = [m.span() for m in URL.finditer(text)]
    for m in WORD.finditer(text):
        word = m.group()
        if len(word) < 2:
            continue
        if any(start <= m.start() < end for start, end in urls):
            continue
        if word.isupper() and not settings.spell_capitals:
            continue
        if (
            not settings.spell_bold_names
            and word[0].isupper()
            and prose.bold[m.start()]
        ):
            continue
        yield m, normalise(word)


def ask_aspell(words: list[str], dictionary: str) -> dict[str, list[str]]:
    """Return {word: suggestions} for the words aspell does not know."""
    if not shutil.which("aspell"):
        raise SpellerMissing("aspell is not installed (brew install aspell)")
    lines = "".join(f"^{w}\n" for w in words)
    result = subprocess.run(
        ["aspell", "-a", "-d", dictionary, "--encoding=utf-8"],
        input=lines, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise SpellerMissing(f"aspell failed: {result.stderr.strip()}")

    # After the banner, each input line yields zero or more result lines then a blank line.
    unknown: dict[str, list[str]] = {}
    replies = result.stdout.split("\n")[1:]
    index = 0
    for word in words:
        while index < len(replies) and replies[index] != "":
            reply = replies[index]
            if reply.startswith("&"):
                head, _, tail = reply.partition(": ")
                unknown[word] = [s.strip() for s in tail.split(",")][:4]
            elif reply.startswith("#"):
                unknown[word] = []
            index += 1
        index += 1
    return unknown


def run(prose, settings) -> list[Finding]:
    accepted = ALWAYS_ACCEPT | load_wordlists(settings.wordlists)
    occurrences = [
        (m, word) for m, word in candidates(prose, settings) if word.lower() not in accepted
    ]
    distinct = sorted({word for _, word in occurrences})
    unknown = ask_aspell(distinct, settings.dictionary) if distinct else {}

    # Only words aspell does not know are looked up, so a place never hides a real word.
    places = {w for w in unknown if settings.places and is_place(w, settings.places)}
    for word in places:
        del unknown[word]
    british = dictionaries.load() if settings.british else None
    macos = dictionaries.ask_macos(sorted(unknown)) if settings.macos else set()
    settings.stats[NAME] = {
        "places": len(places),
        "gazetteer": settings.places is not None,
        "words": len(unknown),
        "british": british is not None,
        "elsewhere": dictionaries.second_opinions(sorted(unknown), british, macos),
    }
    return [
        Finding(NAME, m.start(), m.end(), word, suggestions=unknown[word], group=word)
        for m, word in occurrences
        if word in unknown
    ]
