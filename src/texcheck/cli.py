"""Command line: tex-check FILE [options]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, places
from .checks import STAGES, Settings, resolve
from .checks.spelling import SpellerMissing
from .prose import Source, extract
from .report import Style, as_json, dump_json, print_report

WORDLIST_NAME = "tex-check-words.txt"

EPILOG = f"""\
stages (run in this order):
{chr(10).join(f"  {s.NAME:<12} {s.BLURB}" for s in STAGES)}

examples:
  tex-check document.tex                    every stage
  tex-check document.tex --only repeats     just "the the"
  tex-check document.tex --only punct,spell
  tex-check document.tex --skip grammar
  tex-check document.tex --list-unknown >> tex-check-words.txt
  tex-check document.tex --json | jq '.[] | select(.stage=="spelling")'
  tex-check --update-places --countries GB,IE,FI

word list: words aspell should accept (names, slang), one per line, are read
from {WORDLIST_NAME} beside the .tex file if it exists, and from any --words file.

place names: after `tex-check --update-places`, capitalised words found in the
GeoNames gazetteer (GeoNames, CC BY 4.0) are accepted. It is saved in
{places.places_file()}.

exit status: 0 nothing found, 1 findings, 2 error.
"""


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="tex-check",
        description="Proofread the prose in LaTeX files: repeated words, spacing and "
        "punctuation, spelling and grammar. LaTeX commands are never reported.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="*", type=Path, metavar="FILE", help=".tex file(s) to check")
    p.add_argument("--only", metavar="STAGES", help="comma-separated stages to run")
    p.add_argument("--skip", metavar="STAGES", help="comma-separated stages to leave out")
    p.add_argument("--words", action="append", type=Path, default=[], metavar="FILE",
                   help="extra word list for the spelling stage (repeatable)")
    p.add_argument("--dict", default="en_GB-ise", metavar="NAME",
                   help="aspell dictionary (default: en_GB-ise; see `aspell dicts`)")
    p.add_argument("--spell-bold", action="store_true",
                   help="also spell-check bold capitalised words (names, by house style)")
    p.add_argument("--spell-capitals", action="store_true",
                   help="also spell-check ALL-CAPS words (acronyms)")
    p.add_argument("--no-places", action="store_true",
                   help="do not accept place names from the gazetteer")
    p.add_argument("--update-places", action="store_true",
                   help="download GeoNames place names for the spelling stage, then exit")
    p.add_argument("--countries", default=",".join(places.DEFAULT_COUNTRIES), metavar="CC,..",
                   help="with --update-places: countries to include in full, as ISO codes "
                   "(default: GB,IE; world towns are always included)")
    p.add_argument("--list-unknown", action="store_true",
                   help="print each unknown word once, plain, for building a word list")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--no-colour", "--no-color", action="store_true", help="plain output")
    p.add_argument("--version", action="version", version=f"tex-check {__version__}")
    return p.parse_args(argv)


def choose_stages(args):
    names = [s.NAME for s in STAGES]
    if args.only:
        names = [s.NAME for s in resolve(args.only.split(","))]
    if args.skip:
        dropped = {s.NAME for s in resolve(args.skip.split(","))}
        names = [n for n in names if n not in dropped]
    if args.list_unknown:
        names = ["spelling"]
    return resolve(names)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.update_places:
        return update_places(args.countries)
    if not args.files:
        print("tex-check: give a .tex file to check (see --help)", file=sys.stderr)
        return 2
    try:
        stages = choose_stages(args)
    except ValueError as err:
        print(f"tex-check: {err}", file=sys.stderr)
        return 2

    gazetteer = None if args.no_places else places.load()
    style = Style(colour=not args.no_colour and not args.json and sys.stdout.isatty())
    any_findings = False
    json_items: list[dict] = []
    unknown_words: set[str] = set()

    for path in args.files:
        if not path.is_file():
            print(f"tex-check: no such file: {path}", file=sys.stderr)
            return 2
        source = Source(read(path), str(path))
        prose = extract(source.text)

        local_list = path.parent / WORDLIST_NAME
        settings = Settings(
            dictionary=args.dict,
            wordlists=([local_list] if local_list.is_file() else []) + args.words,
            spell_bold_names=args.spell_bold,
            spell_capitals=args.spell_capitals,
            places=gazetteer,
        )

        results = []
        for stage in stages:
            try:
                findings = stage.run(prose, settings)
            except SpellerMissing as err:
                results.append((stage, str(err)))
                continue
            any_findings |= bool(findings)
            if stage.NAME == "spelling":
                unknown_words |= {f.group for f in findings}
            results.append((stage, findings))

        if args.list_unknown:
            continue
        if args.json:
            json_items += as_json(path, source, prose, results)
        else:
            print_report(path, source, prose, results, style, settings.stats)

    if args.list_unknown:
        for word in sorted(unknown_words, key=str.lower):
            print(word)
    elif args.json:
        dump_json(json_items)
    return 1 if any_findings else 0


def update_places(countries: str) -> int:
    codes = [c.strip().upper() for c in countries.split(",") if c.strip()]
    print(f"Building the place-name list ({', '.join(codes)} + world towns) from GeoNames…")
    try:
        path, count = places.update(codes, say=print)
    except (OSError, KeyError) as err:
        print(f"tex-check: download failed: {err}", file=sys.stderr)
        return 2
    print(f"Saved {count:,} place-name words to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
