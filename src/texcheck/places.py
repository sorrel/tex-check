"""A place-name gazetteer for the spelling stage, built from GeoNames.

`tex-check --update-places` downloads GeoNames country files (every named
place: towns, villages, rivers, hills, buildings) plus `cities1000` (every
town in the world with 1,000+ people, with its other-language names, such
as Trondhjem and Viipuri). From those it keeps each capitalised word of three
or more letters and saves one per line in places.txt.

The spelling stage then accepts a capitalised word found in the list.
Lower-case words are always checked, so a typo that happens to match a place
("bath", "reading") is still caught.

Data: GeoNames (https://www.geonames.org), licensed CC BY 4.0.
"""

import io
import os
import re
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

SOURCE = "https://download.geonames.org/export/dump/{}.zip"
WORLD = "cities1000"
DEFAULT_COUNTRIES = ["GB", "IE"]

TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
POSSESSIVE = re.compile(r"['’]s$")


def data_dir() -> Path:
    override = os.environ.get("TEX_CHECK_DATA")
    return Path(override) if override else Path.home() / ".local" / "share" / "tex-check"


def places_file() -> Path:
    return data_dir() / "places.txt"


def latin(text: str) -> bool:
    """True for names written in Latin script (keeps Tromsø, drops Тромсё)."""
    return all(ord(ch) < 0x250 or not ch.isalpha() for ch in text)


def name_tokens(name: str) -> set[str]:
    return {t for t in TOKEN.findall(name) if len(t) > 2 and t[0].isupper()}


def tokens_from(table: str, with_alternates: bool) -> set[str]:
    """Capitalised words from a GeoNames table (tab-separated, see its readme)."""
    words: set[str] = set()
    for row in table.splitlines():
        cols = row.split("\t")
        if len(cols) < 4:
            continue
        words |= name_tokens(cols[1]) | name_tokens(cols[2])
        if with_alternates and cols[3]:
            for alt in cols[3].split(","):
                if latin(alt):
                    words |= name_tokens(alt)
    return words


def download(name: str, say=print) -> str:
    url = SOURCE.format(name)
    say(f"  downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    return archive.read(f"{name}.txt").decode("utf-8")


def update(countries: list[str], say=print) -> tuple[Path, int]:
    """Download GeoNames for `countries` plus world towns; write places.txt."""
    words: set[str] = set()
    for code in countries:
        # Alternate names in whole-country files are mostly noise (codes, other
        # scripts) and, for big countries, very many; the main names suffice.
        words |= tokens_from(download(code.upper(), say), with_alternates=False)
    words |= tokens_from(download(WORLD, say), with_alternates=True)

    path = places_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# tex-check place names, built {date.today().isoformat()}\n"
        f"# countries: {','.join(c.upper() for c in countries)} + {WORLD}\n"
        f"# source: GeoNames (https://www.geonames.org), CC BY 4.0\n"
    )
    path.write_text(header + "\n".join(sorted(words)) + "\n", encoding="utf-8")
    return path, len(words)


def load() -> set[str] | None:
    """The saved place names, or None if --update-places has not been run."""
    path = places_file()
    if not path.is_file():
        return None
    return {
        line for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }


def is_place(word: str, places: set[str]) -> bool:
    """A capitalised word that names a place (or a place's: "Lewes's")."""
    if not word[:1].isupper():
        return False
    if word in places:
        return True
    base = POSSESSIVE.sub("", word)
    # Only strip 's from longer names: "Her's" must not pass as the town of Her.
    return base != word and len(base) >= 4 and base in places
