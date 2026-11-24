# tex-check

Proofreads the prose in LaTeX files, in stages: **repeats** ("the the"),
**near-repeats** (the same longer word again within a few words),
**punctuation** (double spaces, stray/doubled marks, words run together,
brackets), **spelling** (aspell, `en_GB-ise`), **grammar** (rule-based
heuristics). Stdlib only; aspell is the one external tool (`brew install aspell`).

## How it fits together

- `prose.py`: `Prose`, plain text in which every character keeps its
  source offset, so checks are simple regexes over clean English and still
  report the true line:column; `Source` maps offsets to lines.
- `latex.py`: the one-pass reader that writes `Prose` (`extract`). Plain
  text is copied in runs, not a character at a time. `commands.py` holds
  its tables (`DROP_ARGS`, `HEADINGS`, `NOTES`, `BOLD`, `QUOTES`, ...):
  teach it a new macro by adding it to a table, not by writing code.
  Unlisted commands vanish and their `{groups}` are read as text.
- `src/texcheck/checks/`: one module per stage (`NAME`, `TITLE`, `BLURB`,
  `run(prose, settings)`); order and registry in `checks/__init__.py`.
  New stage = new module + add it to `STAGES`.
- `run.py`: `check_file`, the one run shared by the terminal, `--json` and
  the browser, so all three agree. Word lists are read afresh on each run.
- `groups.py`: sorts findings into groups. Spelling is split into likely
  typos, other, in quotations, foreign/bold, names, variants (shown in that
  order); the rules are evaluated in a different order (see `classify`).
- `progress.py`: the one-line status on stderr (terminal only) for a step
  over a second. `check_file(progress=)` names each stage; stages name slow
  sub-steps through `settings.progress`; `pdfwords.read(say=)` only when
  the PDF is not cached.
- `report.py`: terminal layout (shared `scripts/` conventions) and `--json`;
  `terminal.py` has the styles, headings and paths it uses.
- `wordlists.py`: the book's `tex-check-words.txt` and the personal
  `words.txt` at this repo's root (found via the editable install; falls
  back to `~/.local/share/tex-check/words.txt`).
- `donelog.py`: `tex-check-done.jsonl` beside the book, append-only: every
  OK, add and undo. OK marks are derived from it and match on stage + text
  + `before[[hit]]after` context (never the line), so they survive edits
  elsewhere. Undo is an entry; undoing an add removes the word only if that
  add wrote it (`added`).
- `groups.reason`: plain-words reason per word, from aspell's suggestions
  (missing apostrophe, capitals, one/two words, accent, American, British
  form aspell lacks, plural only, macro slip).
- `dictionaries.py`: second opinions on words aspell rejects: SCOWL 70 GB
  -ise (`--update-dictionary` → `~/.local/share/tex-check/british.txt`) and
  macOS's NSSpellChecker en_GB via one bounded `osascript` call. A word
  either knows goes to the "elsewhere" group unless its reason is in
  `groups.STRONG_REASONS`. macOS also accepts words "learned" on this Mac,
  so its yes is weak. `tests/conftest.py` turns both off for other tests.
- `differences.py`: says how each suggestion differs ("missing a c", "extra
  l", "r and c swapped") and marks the changed letters, since a doubled or
  missing letter is easy to miss by eye.
- `web/`: `tex-check FILE --web`, mail-triage's pattern on a small scale.
  stdlib `http.server` on 127.0.0.1:8766, per-run token (URL once, then
  header; cookie for assets), Host/Origin checks (`security.py`, adapted
  from mail-triage). `routes.py` is a pure `Router.handle(Request)`;
  `session.py` issues opaque ids per check (an old id gets 409, never a
  wrong line); `watcher.py` polls mtimes and re-checks 30 s after the last
  save (each save restarts the wait). Static files are hand-written, no
  build step, no external requests.

## Decisions worth knowing

- `\\`, headings, environments and `\item` become paragraph breaks, so lyric
  lines (`\begin{words}{a\\b}`) are never joined or treated as one sentence.
- Footnotes are moved to the end of the prose and checked as their own
  paragraphs, so the sentence they interrupt reads whole.
- House style bolds names (`\textbf{The The}`): bold capitalised words are
  skipped by spelling (`--spell-bold` to include) and never count as repeats.
- Double spaces are reported only if adjacent in the source, not ones left
  behind by a removed command. TeX collapses them in print anyway.
- aspell's en_GB dictionaries lack some good words (among, learned, dreamt,
  ...): see `ALWAYS_ACCEPT` in `checks/spelling.py`.
- Place names: `tex-check --update-places [--countries GB,IE,FI]` builds
  `~/.local/share/tex-check/places.txt` (about 770,000 words, 8 MB) from
  GeoNames (CC BY 4.0): every named place in the given countries plus world
  towns of 1,000+ with their Latin-script alternate names (Trondhjem,
  Viipuri). Spelling accepts a word only if aspell rejects it, it is
  capitalised, and it is in the list. `'s` is stripped only from bases of 4+
  letters ("Her's" must not pass as the town of Her). `--no-places` turns
  it off. Add countries a text needs (e.g. FI for Finnish places).
- Locations print as `file:line:col` so iTerm can Cmd-click them.
- `tex-check-open FILE:LINE:COL` (`opener.py`) opens Texifier at a finding.
  Texifier 1.9.33 cannot be told a line: URL schemes only open files,
  AppleScript is the standard suite, File › Jump to (⇧⌘O) is Tag Search,
  setting AXSelectedTextRange is silently ignored, and ⌘G ignores the system
  find pasteboard. What works (tested 22 November 2026): put the shortest
  phrase from line:col that is unique in the file on the find pasteboard,
  focus the editor ("Text View" in "Editor"), ⌘F, Return, Escape. Focus
  matters: with the sidebar focused, ⌘F opens the sidebar search instead.
  Needs Accessibility for iTerm (granted). iTerm (3.7.9) Semantic History
  › Run command: `~/.local/bin/tex-check-open
  "\(semanticHistory.path)" "\(semanticHistory.lineNumber)"
  "\(semanticHistory.columnNumber)"`; non-.tex files fall back to `open`.
- Word lists: per book (`tex-check-words.txt` beside the .tex) for names,
  dialect and invented words; personal (`words.txt` here, gitignored since the repository went
  public: adds are often names) for good
  words everywhere. Bootstrap a book's with `--list-unknown`, then prune.
- Grouping heuristics were tuned on a real 3,400-line book (22 November
  2026: 209 words → typos 49, other 7, quotes 21, bold 20, names 55,
  variants 57). Variants must be tested after quotes and bold: aspell splits almost
  anything ("secours" → "sec ours"). Likely typos are still mostly good
  words aspell lacks, and hyphenated fragments (*pre*-, *-seater*); the
  personal list absorbs the first.
- Not yet confirmed: whether `--web`'s Open in Texifier inherits iTerm's
  Accessibility permission (it should: the server is started from iTerm).

- Near-repeats (`checks/near_repeats.py`) were tuned on a 106,000-word
  book: 40 words for every word gave 1,398 findings, nearly all subject
  words (people, school). Now: within 25 words if the word is used 6 times
  or fewer in the text, within 4 otherwise; about 230. Paragraphs under 12
  words (lyric lines, headings) break the window.

- Layout (`checks/layout/`: `find.py` the checks and thresholds,
  `repair.py` run-together words, `match.py` back to the prose; and
  `pdfwords.py`): reads `document.pdf` beside
  `document.tex` through PDFKit (`osascript -l JavaScript`), macOS only.
  Lessons (23 November 2026): xpdf's pdftotext/pdftohtml give no word
  positions; PDFKit's page text and `characterBoundsAtIndex` disagree (line
  breaks, boxes too wide on some lines), so each letter is read as a
  one-letter selection and words are built from the gaps: about 80 s for a
  290-page book, cached by PDF size+mtime in `~/.local/share/tex-check/
  layout-cache`. Some lines still come back with touching boxes and no
  spaces; `layout.unglue` splits them with the book's own vocabulary.
  Findings map back to the prose by anchors (4-token runs unique in both,
  longest increasing chain) and difflib between them: the contents pages
  defeat a simple cursor. Margins are the mode of line edges, not min/max
  (a stray mark at x=0 on every page). No SyncTeX file is written here.

## Publishing

The repository is public. Nothing personal goes in it: no home paths,
book titles, document excerpts or addresses. `tests/test_no_personal_data.py`
enforces this; its denylist of identifying terms lives in the gitignored
`local/identifying-terms.txt`, because listing a term in order to assert
its absence would publish it.

## Not done yet

- A LanguageTool stage for real grammar checking. Local LanguageTool needs
  Java 17+: `/usr/bin/java` is 11, but Homebrew's keg-only openjdk (27) is
  installed at `/opt/homebrew/opt/openjdk/bin/java`, so it can run locally.
  The public API would send the text off the machine: ask before that.
- Layout thresholds (`checks/layout/find.py` constants) are the user's to set;
  "directly above" means centres within 10% of the word width (askew is
  fine, by request); still the largest group.
- A tense check (an unintended slip from past to present in narration,
  ignoring dialogue). Regexes cannot do it: it needs a tagger, LanguageTool
  or a model, and the latter two may send text off the machine, so ask.

## Running

    uv tool install --editable .     # once; gives `tex-check` on PATH
    tex-check document.tex --only repeats
    tex-check document.tex --web     # browser view
    uv run pytest                    # tests (CI runs them on 3.12 too)
    uvx ruff check                   # lint, config in pyproject.toml
