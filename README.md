# tex-check

Proofread the prose in a LaTeX file. LaTeX commands are never reported, and
every finding points at the line and column in your `.tex` source.

```
Repeated words  the same word twice in a row ──────────────────── 1
  chapter1.tex:212:31   “the the”
                        …she put the the kettle on and \textbf{waited}…
```

It runs in four stages, which you can run together or one at a time:

| Stage | Finds |
|---|---|
| `repeats` | the same word twice in a row, even across markup (`the \textbf{the}`) |
| `punctuation` | double spaces, space before a comma, `,,` `..` `.,`, words run together (`to\textbf{The}`), unbalanced brackets |
| `spelling` | unknown words, via aspell (British English by default), with suggestions |
| `grammar` | common slips: *a apple*, *could of*, *more then*, *its a*, *your welcome*, *her's*, lower-case *i* |

## Install

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/), and aspell for the spelling stage:

```
brew install aspell
uv tool install --editable .
```

## Use

```
tex-check book.tex                      # every stage
tex-check book.tex --only repeats       # one stage (or a list: punct,spell)
tex-check book.tex --skip grammar
tex-check book.tex --json               # for other tools
tex-check book.tex --web                # in the browser (see below)
```

Spelling findings are sorted into groups, likely typos first: **Likely
typos**, **In quotations** (dialogue, dialect), **Foreign and bold
phrases**, **Names** and **Variants** (*ok*/OK, *heathland*/heath land),
plus **Other unknown words** for anything aspell has no suggestion for.
Web addresses are not spell-checked.

Each word also says **why** it was flagged, worked out from aspell's
suggestions, which on their own never explain:

```
  document.tex:786:167   Ziggys        ×2   missing apostrophe?   → Ziggy's, Ziggy, Piggy's
  document.tex:404:46    synthesisers       British spelling; aspell knows only the American
  document.tex:2162:304  accoutrement       aspell knows only the plural
  document.tex:485:282   practiced          American spelling?    → practised, …
```

Others: *capitals differ*, *usually two words*, *usually hyphenated*,
*accent differs*, *missing \ before \bsq?* (a command that lost its
backslash), and *not in the dictionary*.

Exit status: 0 nothing found, 1 findings, 2 error. `tex-check --help` lists
every option.

**Word lists.** Words aspell doesn't know but you do go in one of two lists,
one per line:

- `tex-check-words.txt` beside the `.tex` file, for that book's names,
  dialect and invented words. It travels with the book.
- `words.txt` in this repository, for good words everywhere (*heathland*,
  *Ericsson*). It is in git, so mistakes show in the history.
  `--no-personal-words` leaves it out.

To start a book's list:

```
tex-check book.tex --list-unknown > tex-check-words.txt   # then delete the real typos
```

To accept place names automatically, download a gazetteer once (about
8 MB, from [GeoNames](https://www.geonames.org)):

```
tex-check --update-places --countries GB,IE      # add any countries your text needs
```

Bold capitalised words (`\textbf{Name}`) and ALL-CAPS words are not
spell-checked: `--spell-bold` and `--spell-capitals` include them. Another
dictionary: `--dict en_US` (see `aspell dicts`).

## In the browser

```
tex-check book.tex --web            # opens http://127.0.0.1:8766/
tex-check book.tex --web --no-open --port 9000
```

The groups are down the side. Every **use** of a word is its own row, with
its context, **Open in Texifier** and **OK** ("fine here": hides that one
place only). A word's header has its reason, aspell's suggestions, and
**Add for this book** / **Add everywhere** for all its uses at once.

Every OK and every add is recorded, and the **Done** view lists them
newest first with an **Undo** button, so a wrong click can always be found
and put back. OK marks are matched on the text around the finding, not its
line number, so they survive edits elsewhere and lapse if you rewrite that
sentence. The terminal report leaves OK'd findings out too.

Keys: `j`/`k` move, `o` open in Texifier, `x` OK, `b` add for this book,
`e` add everywhere.

Save in Texifier and the page re-checks 30 seconds after the last save;
each further save restarts the wait, or press **Re-check now**. Stop it by
typing `q` (or `quit`, `exit`) and Return, or ctrl-C; it also stops by itself 30 minutes after the page is closed.

The server listens on 127.0.0.1 only and every request needs the token in
the address it opens, so no other web page can press its buttons.

## Files it keeps

| File | Where | What |
|---|---|---|
| `tex-check-words.txt` | beside the `.tex` | this book's accepted words |
| `tex-check-done.jsonl` | beside the `.tex` | every OK, add and undo (append-only) |
| `words.txt` | this repository | your accepted words for every book |
| `places.txt` | `~/.local/share/tex-check/` | the GeoNames place names |

Nothing is sent anywhere: the only network use is the one-off GeoNames
download.

## Jump to a finding in Texifier (macOS, optional)

`tex-check-open book.tex:212:31` opens the file in
[Texifier](https://www.texifier.com) with the text at that point selected.
To get there by Cmd-clicking a location in an [iTerm](https://iterm2.com)
report:

1. System Settings › Privacy & Security › Accessibility: turn on **iTerm**.
2. iTerm › Settings › Profiles › Advanced › Semantic History › **Run command…**:

   ```
   ~/.local/bin/tex-check-open "\(semanticHistory.path)" "\(semanticHistory.lineNumber)" "\(semanticHistory.columnNumber)"
   ```

Files other than `.tex` still open in their default app.

## Development

```
uv run pytest
```

Each stage is one module in `src/texcheck/checks/`. `CLAUDE.md` explains the
design and the decisions behind it.

Place-name data © GeoNames, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Code under the MIT licence.
