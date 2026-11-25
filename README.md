# tex-check

Proofread the prose in a LaTeX file. LaTeX commands are never reported, and
every finding points at its line and column in your `.tex` source.

```
Repeated words  the same word twice in a row ──────────────────── 1
  chapter1.tex:212:31   “the the”
                        …she put the the kettle on and \textbf{waited}…
```

## 🔍 What it checks

| Stage | Finds |
|---|---|
| `repeats` | the same word twice in a row, even across markup (`the \textbf{the}`) |
| `near-repeats` | a longer word again a few words later |
| `punctuation` | double spaces, `,,` `..` `.,`, a space before a comma, words run together, unbalanced brackets |
| `spelling` | unknown words (aspell, British English), with suggestions and a reason |
| `grammar` | common slips: *a apple*, *could of*, *more then*, *its a*, lower-case *i* |
| `languagetool` | grammar, usage and style from [LanguageTool](https://languagetool.org), run on your Mac (*I didn't understood*, a noun *license*, *twenty year-old*); grouped so likely mistakes come before comma advice |
| `tense` | a present-tense sentence alone in past-tense narration (*We walked to the river. The water **is** cold. Then we went home.*), dialogue aside; uses LanguageTool's tagger |
| `layout` | the typeset PDF (macOS): a heading with under three lines below it at the foot of a page, a part page on a left-hand page, one-word last lines, lone *I*s at line edges, a word starting, ending or sitting squarely above itself on the next line, the same word on three lines running (four or more shown on their own) |

LanguageTool is optional (`brew install languagetool`; without it the stage
says so and is skipped). tex-check starts it on 127.0.0.1 for the run and
stops it after: your text never leaves the machine. A long book takes about
ten seconds, and the tense check about as long again. `--skip lt,tense`
leaves them out.

Layout needs `document.pdf` beside `document.tex`. Its first run reads every
letter's position (about a minute for a long book); after that it is cached
until you typeset again.

## 📦 Install

Needs Python 3.14+, [uv](https://docs.astral.sh/uv/) and aspell
(LanguageTool optional):

```
brew install aspell languagetool
uv tool install --editable .
```

## ▶️ Use

```
tex-check book.tex                   # every stage
tex-check book.tex --only spell      # one stage, or a list: punct,spell
tex-check book.tex --skip grammar
tex-check book.tex --web             # in the browser
tex-check book.tex --json            # for other tools
```

⏳ A step that takes more than a second (reading a PDF for the first time,
asking macOS's dictionary) shows what it is doing and for how long, on one
line that clears when the report starts.

Exit status: 0 nothing found, 1 findings, 2 error. `tex-check --help` lists
every option.

## 🔤 Spelling

Findings are grouped so the likely mistakes come first: **Likely typos**,
**Other unknown words**, **In quotations**, **Foreign and bold phrases**,
**Names** and **Variants**. **Probably correct** comes after everything
else (see below).

Each word says why it was flagged, and each suggestion says how it differs,
with the changed letters underlined, because a doubled or missing letter is
easy to miss by eye:

```
  Ziggys        ×2   missing apostrophe?   → Ziggy's, Ziggy, Piggy's
  lyrca              not in the dictionary → Lycra (r and c swapped, capital L), Lyra
  laundrette         not in the dictionary → launderette (missing an e)
```

aspell's British dictionary is small, so two larger ones give a second
opinion: macOS's own British spellchecker, and the SCOWL British word list
(download it once with `tex-check --update-dictionary`). A word either one
knows moves to *Probably correct*, shown last. macOS also accepts words
"learned" on this Mac, so a word only it knows is marked *only this Mac
knows it*. `--no-macos` and `--no-british` turn them off.

**Word lists**, one word per line:

- `tex-check-words.txt` beside the `.tex`: this book's names and dialect.
  Start one with `tex-check book.tex --list-unknown > tex-check-words.txt`,
  then delete the real typos.
- `words.txt` in this folder: good words for every book. It is gitignored,
  so names you add stay private.

**Place names:** `tex-check --update-places --countries GB,IE` downloads
GeoNames (about 8 MB) once, and capitalised place names are then accepted.

Bold capitalised words (names, in this house style) and ALL-CAPS words are
skipped unless you add `--spell-bold` or `--spell-capitals`.

## 🌐 In the browser

```
tex-check book.tex --web             # opens http://127.0.0.1:8766/
```

Every use of a word is a row with **Open in Texifier** and **OK** (fine
here). A word's header has **Add for this book** and **Add everywhere**.
Keys: `j`/`k` move, `o` open, `x` OK, `b` add for this book, `e` add
everywhere.

The **Done** view lists every OK and add, newest first, each with **Undo**.
OK marks follow the text, not the line number, so they survive edits
elsewhere.

Save in Texifier and the page re-checks 30 seconds after your last save.
Type `q` and Return (or ctrl-C) to stop; it also stops by itself 30 minutes
after the page is closed.

🔒 The server listens on 127.0.0.1 only, and every request needs the token
from the address it opens, so no other web page can press its buttons.

## 📁 Files it keeps

| File | Where | What |
|---|---|---|
| `tex-check-words.txt` | beside the `.tex` | this book's accepted words |
| `tex-check-done.jsonl` | beside the `.tex` | every OK, add and undo |
| `words.txt` | this folder (gitignored) | accepted words for every book |
| `places.txt`, `british.txt` | `~/.local/share/tex-check/` | the downloaded word lists |
| `layout-cache/` | `~/.local/share/tex-check/` | word positions read from each PDF |

Nothing leaves your Mac apart from those two one-off downloads.

## 🖱️ Jump to a finding in Texifier

`tex-check-open book.tex:212:31` opens Texifier with the text at that point
selected. To Cmd-click a location in an [iTerm](https://iterm2.com) report:

1. System Settings › Privacy & Security › Accessibility: turn on **iTerm**.
2. iTerm › Settings › Profiles › Advanced › Semantic History › **Run command…**:

   ```
   ~/.local/bin/tex-check-open "\(semanticHistory.path)" "\(semanticHistory.lineNumber)" "\(semanticHistory.columnNumber)"
   ```

## 🛠️ Development

```
uv run pytest        # tests
uvx ruff check       # lint
```

Each stage is a module in `src/texcheck/checks/`. `CLAUDE.md` explains the
design and the decisions behind it.

Place-name data © GeoNames, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Code under the MIT licence.
