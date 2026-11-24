"""The repository is public. Nothing personal may reach it.

tex-check is developed against real, unpublished books. A home path, a book
title or an excerpt is easy to paste into a doc or a test while debugging,
and very hard to spot later. These tests are the mechanical check, over
every tracked file.

The denylist of identifying terms is gitignored (`local/identifying-terms.txt`):
writing a name here in order to assert its absence would publish it. Without
that file the term check is skipped, visibly, as it will be for anyone who
clones the repository, for whom there is nothing to protect.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TERMS_FILE = ROOT / "local" / "identifying-terms.txt"

#: Exact domains, or parents of a domain, that may appear in an address.
#: Matched exactly or as a parent, never as a substring ("example.com.evil").
_ALLOWED_SUFFIXES = ("example.com", "example.org", "example.net", "example",
                     "users.noreply.github.com", "anthropic.com")

_EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
_HOME = re.compile(r"/(?:Users|home)/(?!runner\b)[A-Za-z][\w.-]*")


def _tracked() -> list[Path]:
    names = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [ROOT / name for name in names if name != "uv.lock"]


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return ""


def _allowed(domain: str) -> bool:
    domain = domain.casefold().rstrip(".")
    return any(domain == s or domain.endswith("." + s) for s in _ALLOWED_SUFFIXES)


def test_there_are_files_to_check():
    """Guard against the guard passing on an empty list."""
    assert len(_tracked()) > 10


def test_no_real_email_addresses():
    offences = [
        f"{path.relative_to(ROOT)}: {match.group()}"
        for path in _tracked()
        for match in _EMAIL.finditer(_text(path))
        if not _allowed(match.group(1))
    ]
    assert offences == [], f"possible real addresses: {offences}"


def test_no_home_paths():
    offences = [
        f"{path.relative_to(ROOT)}: {match.group()}"
        for path in _tracked()
        for match in _HOME.finditer(_text(path))
    ]
    assert offences == [], f"home paths: {offences}"


@pytest.mark.skipif(not TERMS_FILE.is_file(), reason="no local/identifying-terms.txt")
def test_no_identifying_terms():
    terms = [
        line.strip().casefold()
        for line in TERMS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    offences = [
        f"{path.relative_to(ROOT)}: {term}"
        for path in _tracked()
        for term in terms
        if term in _text(path).casefold()
    ]
    assert offences == [], f"identifying terms: {offences}"
