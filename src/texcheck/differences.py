"""How a suggestion differs from the misspelt word, in plain words.

A list such as "Eclesall → Ecclesall, Ecclesial" asks the reader to spot a
doubled letter by eye, which is exactly what is hard for some readers (an
extra "l" especially). So each suggestion says what changed ("missing a c",
"extra l", "i and e swapped") and `marked` splits it into runs so a view can
underline the letters that changed.

Only small differences are described (up to two changes); beyond that the
suggestion is a different word, not a correction, and saying so in letters
would be noise.
"""

from __future__ import annotations

import difflib
import unicodedata

#: Letters whose name starts with a vowel sound take "an": an l, an m, an s.
_AN_LETTERS = set("aefhilmnorsx")

_MAX_CHANGES = 2


def _article(letter: str) -> str:
    return "an" if letter.lower() in _AN_LETTERS else "a"


def _strip_accents(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in plain if not unicodedata.combining(ch))


def _straight(text: str) -> str:
    return text.replace("’", "'")


def _swap_at(a: str, b: str) -> int | None:
    """The index i where a and b differ only by a[i], a[i+1] swapped."""
    if len(a) != len(b):
        return None
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]:
        return diff[0]
    return None


def _case_note(word: str, suggestion: str) -> str:
    """Capitals, when the letters match but their case does not."""
    if word.lower() != suggestion.lower() or word == suggestion:
        return ""
    if suggestion.isupper() and len(suggestion) > 1:
        return f"capitals {suggestion}"
    changed = [s for w, s in zip(word, suggestion) if w != s]
    return ", ".join(f"capital {s}" if s.isupper() else f"small {s}" for s in changed)


def _letter_edits(word: str, suggestion: str) -> list[str] | None:
    """The changes from word to suggestion (case ignored), or None if too many."""
    a, b = word.lower(), suggestion.lower()
    swap = _swap_at(a, b)
    if swap is not None:
        return [f"{a[swap]} and {a[swap + 1]} swapped"]
    edits = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        old, new = a[i1:i2], b[j1:j2]
        if op == "insert":
            edits.append(f"missing {_article(new)} {new}" if len(new) == 1 else f"missing “{new}”")
        elif op == "delete":
            edits.append(f"extra {old}" if len(old) == 1 else f"extra “{old}”")
        else:
            edits.append(f"{new} for {old}")
    return edits if len(edits) <= _MAX_CHANGES else None


def describe(word: str, suggestion: str) -> str:
    """How `suggestion` differs from `word`, or "" if it is not a small change."""
    word, suggestion = _straight(word), _straight(suggestion)
    if word == suggestion:
        return ""
    if suggestion.replace("'", "") == word:
        return "missing apostrophe"
    if word.replace("'", "") == suggestion:
        return "extra apostrophe"
    if suggestion.replace(" ", "") == word:
        return "space added"
    if suggestion.replace("-", "") == word:
        return "hyphen added"
    if word.lower() == suggestion.lower():
        return _case_note(word, suggestion)
    if _strip_accents(word).lower() == _strip_accents(suggestion).lower():
        accented = [ch for ch in word if _strip_accents(ch) != ch]
        if accented:
            return "no accent on " + ", ".join(_strip_accents(ch) for ch in accented)
        return "accent on " + ", ".join(ch for ch in suggestion if _strip_accents(ch) != ch)
    edits = _letter_edits(word, suggestion)
    if edits is None:
        return ""
    # Case differences in the letters the two share ("lyrca" → "Lycra").
    a, b = word.lower(), suggestion.lower()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for w, s in zip(word[i1:i2], suggestion[j1:j2]):
                if w != s:
                    edits.append(f"capital {s}" if s.isupper() else f"small {s}")
    return ", ".join(edits)


def marked(word: str, suggestion: str) -> list[tuple[str, bool]]:
    """The suggestion as runs of (text, changed), changed letters marked.

    A letter the suggestion lacks cannot be marked in it; `describe` says
    which ("extra l").
    """
    word, suggestion = _straight(word), _straight(suggestion)
    a, b = word.lower(), suggestion.lower()
    flags = [False] * len(suggestion)
    swap = _swap_at(a, b)
    if swap is not None:
        flags[swap] = flags[swap + 1] = True
    else:
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if op in ("insert", "replace"):
                for j in range(j1, j2):
                    flags[j] = True
    runs: list[tuple[str, bool]] = []
    for ch, flag in zip(suggestion, flags):
        if runs and runs[-1][1] == flag:
            runs[-1] = (runs[-1][0] + ch, flag)
        else:
            runs.append((ch, flag))
    return runs
