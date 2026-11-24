"""Command line: tex-check FILE [options]."""

import argparse
import sys
from pathlib import Path

from . import __version__, dictionaries, donelog, places, wordlists
from .checks import STAGES, resolve
from .groups import group_findings
from .progress import Progress
from .report import Style, as_json, dump_json, print_report
from .run import Options, check_file

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
  tex-check document.tex --web              findings in the browser
  tex-check --update-places --countries GB,IE,FI

word lists: words aspell should accept, one per line, are read from
{wordlists.BOOK_NAME} beside the .tex file (this book's names and dialect), from
the personal list {wordlists.personal_file()} (good words everywhere), and from
any --words file.

place names: after `tex-check --update-places`, capitalised words found in the
GeoNames gazetteer (GeoNames, CC BY 4.0) are accepted. It is saved in
{places.places_file()}.

exit status: 0 nothing found, 1 findings, 2 error.
"""


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="tex-check",
        description="Proofread the prose in LaTeX files: repeated words, spacing and\n"
        "punctuation, spelling, grammar and layout. LaTeX commands are never reported.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="*", type=Path, metavar="FILE", help=".tex file(s) to check")
    p.add_argument("--only", metavar="STAGES", help="comma-separated stages to run")
    p.add_argument("--skip", metavar="STAGES", help="comma-separated stages to leave out")
    p.add_argument("--version", action="version", version=f"tex-check {__version__}")
    _spelling_options(p.add_argument_group("spelling"))
    _download_options(p.add_argument_group("downloads (then exit)"))
    _output_options(p.add_argument_group("output"))
    return p.parse_args(argv)


def _spelling_options(g) -> None:  # an argparse argument group
    g.add_argument("--words", action="append", type=Path, default=[], metavar="FILE",
                   help="extra word list (repeatable)")
    g.add_argument("--dict", default="en_GB-ise", metavar="NAME",
                   help="aspell dictionary (default: en_GB-ise; see `aspell dicts`)")
    g.add_argument("--no-personal-words", action="store_true",
                   help="leave out the personal word list")
    g.add_argument("--spell-bold", action="store_true",
                   help="also check bold capitalised words (names, by house style)")
    g.add_argument("--spell-capitals", action="store_true",
                   help="also check ALL-CAPS words (acronyms)")
    g.add_argument("--no-places", action="store_true",
                   help="do not accept place names from the gazetteer")
    g.add_argument("--no-british", action="store_true",
                   help="do not ask the larger British word list")
    g.add_argument("--no-macos", action="store_true",
                   help="do not ask macOS's British spellchecker")
    g.add_argument("--list-unknown", action="store_true",
                   help="print each unknown word once, plain, for building a word list")


def _download_options(g) -> None:  # an argparse argument group
    g.add_argument("--update-places", action="store_true",
                   help="download GeoNames place names for the spelling stage")
    g.add_argument("--countries", default=",".join(places.DEFAULT_COUNTRIES), metavar="CC,..",
                   help="with --update-places: countries to include in full, as ISO codes "
                   "(default: GB,IE; world towns are always included)")
    g.add_argument("--update-dictionary", action="store_true",
                   help="download the larger British word list (SCOWL, about 1.6 MB)")


def _output_options(g) -> None:  # an argparse argument group
    g.add_argument("--web", action="store_true",
                   help="open the findings in a browser, re-checking after each save")
    g.add_argument("--port", type=int, default=8766, help="with --web: port (default: 8766)")
    g.add_argument("--no-open", action="store_true",
                   help="with --web: print the address instead of opening a browser")
    g.add_argument("--json", action="store_true", help="machine-readable output")
    g.add_argument("--no-colour", "--no-color", action="store_true", help="plain output")


def choose_stages(args: argparse.Namespace) -> list:
    """The stages --only, --skip and --list-unknown leave; ValueError if unknown."""
    if args.list_unknown:
        return resolve(["spelling"])
    names = [s.NAME for s in (resolve(args.only.split(",")) if args.only else STAGES)]
    if args.skip:
        dropped = {s.NAME for s in resolve(args.skip.split(","))}
        names = [n for n in names if n not in dropped]
    return resolve(names)


def _progress() -> Progress:
    """The status line for slow steps, on stderr when it is a terminal."""
    return Progress(sys.stderr, enabled=sys.stderr.isatty())


def _fail(message: str) -> int:
    print(f"tex-check: {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.update_places:
        return update_places(args.countries)
    if args.update_dictionary:
        return update_dictionary()
    if not args.files:
        return _fail("give a .tex file to check (see --help)")
    if args.web and len(args.files) != 1:
        return _fail("--web takes one file")
    try:
        stages = choose_stages(args)
    except ValueError as err:
        return _fail(str(err))
    if missing := next((p for p in args.files if not p.is_file()), None):
        return _fail(f"no such file: {missing}")

    gazetteer = None
    if not args.no_places:
        with _progress() as progress:
            progress.say("Loading place names")
            gazetteer = places.load()
    style = Style(colour=not args.no_colour and not args.json and sys.stdout.isatty())
    if args.web:
        return web(args.files[0], stages, _options(args), gazetteer, args, style)
    return check_files(args, stages, _options(args), gazetteer, style)


def _options(args: argparse.Namespace) -> Options:
    return Options(
        dictionary=args.dict,
        extra_wordlists=tuple(args.words),
        spell_bold=args.spell_bold,
        spell_capitals=args.spell_capitals,
        personal_words=not args.no_personal_words,
        british=not args.no_british,
        macos=not args.no_macos,
    )


def check_files(args: argparse.Namespace, stages: list, options: Options, gazetteer,
                style: Style) -> int:
    """Check every file and print a report each (or JSON, or the unknown
    words). Exit status 1 if anything was found."""
    any_findings = False
    json_items: list[dict] = []
    unknown_words: set[str] = set()
    for path in args.files:
        with _progress() as progress:
            run = check_file(path, stages, options, gazetteer, progress=progress.say)
        for stage, outcome in run.results:
            if isinstance(outcome, list):
                any_findings |= bool(outcome)
                if stage.NAME == "spelling":
                    unknown_words |= {f.group for f in outcome}
        if args.list_unknown:
            continue
        groups = group_findings(run, ok=donelog.ok_marks(donelog.log_file(path)))
        if args.json:
            json_items += as_json(run, groups)
        else:
            print_report(run, groups, style, Path.cwd())

    if args.list_unknown:
        for word in sorted(unknown_words, key=str.lower):
            print(word)
    elif args.json:
        dump_json(json_items)
    return 1 if any_findings else 0


def web(path: Path, stages: list, options: Options, gazetteer, args: argparse.Namespace,
        style: Style) -> int:
    """Serve the browser view of one file until q, ctrl-C or idle."""
    import secrets

    from .web.routes import Router
    from .web.server import serve
    from .web.session import Session

    with _progress() as progress:  # the first check, before the server starts
        session = Session(path, stages, options, gazetteer, progress=progress.say)
    router = Router(session, secrets.token_urlsafe(24), args.port)

    def ready(url: str, port: int, stop) -> None:
        print()
        print(f"{style.bold('tex-check')}  {style.cyan(path.name)}  {style.dim('in the browser')}")
        print(f"  {style.dim('Serving on')} {url}")
        what = "Open that address in a browser" if args.no_open else "Opening your browser…"
        print(f"  {what}   {style.dim('type')} q {style.dim('and Return (or ctrl-C) to stop')}")
        print(flush=True)  # the server holds the terminal from here on

    try:
        serve(router, port=args.port, open_browser=not args.no_open, on_ready=ready,
              keyboard=sys.stdin if sys.stdin.isatty() else None)
    except OSError as err:
        return _fail(f"cannot serve on port {args.port}: {err.strerror or err}")
    return 0


def update_dictionary() -> int:
    """--update-dictionary: fetch the SCOWL British list."""
    print("Downloading the larger British word list (SCOWL size 70, -ise) from wordlist.aspell.net…")
    try:
        count = dictionaries.update()
    except OSError as err:
        return _fail(f"download failed: {err}")
    print(f"Saved {count:,} words to {dictionaries.british_file()}")
    return 0


def update_places(countries: str) -> int:
    """--update-places: build the gazetteer for the given countries."""
    codes = [c.strip().upper() for c in countries.split(",") if c.strip()]
    print(f"Building the place-name list ({', '.join(codes)} + world towns) from GeoNames…")
    try:
        path, count = places.update(codes, say=print)
    except (OSError, KeyError) as err:
        return _fail(f"download failed: {err}")
    print(f"Saved {count:,} place-name words to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
