"""Second opinions on the words aspell rejects.

aspell's en_GB-ise dictionary is small: synthesisers, accoutrement,
heathland and laundrette are all "unknown" to it. Two larger dictionaries
are asked about the words aspell rejects, and only those:

* **The larger British list**: SCOWL size 70, British -ise spelling, from
  wordlist.aspell.net (Kevin Atkinson; free to use, copy and distribute).
  Strict: it rejects American forms such as *practiced*. Downloaded once
  by `tex-check --update-dictionary` to ~/.local/share/tex-check/british.txt.
* **macOS's own spellchecker** (NSSpellChecker in British English), the one
  Texifier underlines with. Broad, but it also accepts words someone has
  "learned" on this Mac, so its yes is weaker.

Neither is the judge. A word either knows is moved out of Likely typos to a
group of its own, saying which knew it; `groups.classify` keeps it where it
was if its reason is a strong one (a missing apostrophe, say). Nothing
leaves the machine except the one-off download.
"""

from __future__ import annotations

import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .places import data_dir

SOURCE = (
    "https://app.aspell.net/create?max_size=70&spelling=GBs&max_variant=0"
    "&diacritic=both&special=hacker&download=wordlist&encoding=utf-8&format=inline"
)

#: How long macOS may take to answer, in seconds. It is one call per check.
MACOS_TIMEOUT = 30

#: Asks NSSpellChecker in British English; prints the words it accepts.
_MACOS_SCRIPT = """
use framework "AppKit"
use scripting additions
on run argv
	set checker to current application's NSSpellChecker's sharedSpellChecker()
	checker's setLanguage:"en_GB"
	set known to {}
	repeat with w in argv
		set r to (checker's checkSpellingOfString:(w as text) startingAt:0)
		if (|length| of r) is 0 then set end of known to (w as text)
	end repeat
	set AppleScript's text item delimiters to linefeed
	return known as text
end run
"""


def british_file() -> Path:
    return data_dir() / "british.txt"


def words_from(text: str) -> list[str]:
    """The words of a SCOWL 'inline' word list: everything after the '---' line."""
    lines = text.splitlines()
    if "---" in lines:
        lines = lines[lines.index("---") + 1:]
    return [line.strip() for line in lines if line.strip()]


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "tex-check"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def update(target: Path | None = None, fetch: Callable[[str], bytes] = _download) -> int:
    """Download the larger British list and save it; return its word count."""
    target = target or british_file()
    words = words_from(fetch(SOURCE).decode("utf-8"))
    if len(words) < 3:
        raise OSError("the word list came back empty")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".part")
    temporary.write_text("\n".join(words) + "\n", encoding="utf-8")
    temporary.replace(target)
    return len(words)


def load(path: Path | None = None) -> set[str] | None:
    """The larger British list, lower-cased, or None if not downloaded."""
    path = path or british_file()
    if not path.is_file():
        return None
    return {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def ask_macos(words: list[str], run: Callable = subprocess.run,
              platform: str = sys.platform) -> set[str]:
    """The words macOS's British spellchecker accepts. Empty off macOS or on failure."""
    if platform != "darwin" or not words:
        return set()
    try:
        result = run(["osascript", "-", *words], input=_MACOS_SCRIPT, capture_output=True,
                     text=True, timeout=MACOS_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return set()
    if result.returncode != 0:
        return set()
    asked = set(words)
    return {line for line in result.stdout.splitlines() if line in asked}


def second_opinions(words: list[str], british: set[str] | None,
                    macos: set[str]) -> dict[str, str]:
    """{word: which dictionary knew it} for the words either one accepts."""
    notes = {}
    for word in words:
        in_list = british is not None and word.replace("’", "'").lower() in british
        on_mac = word in macos
        if in_list and on_mac:
            notes[word] = "in the larger British list and known to macOS"
        elif in_list:
            notes[word] = "in the larger British list"
        elif on_mac:
            notes[word] = "known to macOS"
    return notes
