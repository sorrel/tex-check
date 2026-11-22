# Grouped findings, and a browser view

Design. 22 November 2026.

## The problem

A run over a real book (`document.tex`, about 3,400 lines)
gave 217 findings, 213 of them spelling, and the report was hard to use:

- Every finding starts with the full absolute path (about 70 columns), so
  the word, the suggestions and the context are pushed to the right or wrap.
- Spelling is one flat list in file order. The handful of real typos
  (*lyrca*, *Eclesall*, *Drusillias*, *bsqentertainment*) are buried among
  foreign phrases, accented dialogue (*vould*, *goot*), names and brands
  (*Ericsson* ×18), spelling variants (*ok*, *ethernet*) and URL fragments
  (*https*, *uk*).
- Acting on a finding means leaving the report: Cmd-click to open Texifier,
  or editing `tex-check-words.txt` by hand.

## What the user wants

1. Findings **sorted into groups**, so the likely mistakes come first and
   whole classes of non-mistakes can be passed over at a glance.
2. To **open Texifier at any finding, at any point**, not only in sequence.
3. A browser view, along the lines of `../mail-triage`'s web interface.
4. The view to **re-check the file after edits**, but without stuttering:
   re-check 30 seconds after a save, and a further save restarts the 30
   seconds.

## Goals, non-goals, anti-goals

Goals: grouped findings in both the terminal and the browser; one click to
open Texifier at a finding; one click to add a word to the word list;
automatic re-check after edits settle.

Non-goals: editing the .tex from the browser; persistent "ignore this
finding" state (the word list is the persistent mechanism); several files
in one browser session; a LanguageTool stage.

Anti-goals: anything reachable from off the machine; any external request
from the page (fonts, CDNs); a re-check that fires on every keystroke-save;
runtime dependencies (the project is stdlib-only and stays so).

## Approaches considered

- **A. Interactive terminal mode (`-i`)**: step through findings one at a
  time with single-key actions. Sequential by nature, so opening "any
  finding at any point" means paging to it.
- **B. Better static terminal report only**: groups and shorter paths, but
  not interactive; acting still means Cmd-click and hand-editing.
- **C. B plus an interactive view.** Chosen, with the interactive view in
  the browser rather than the terminal (the user's suggestion), because the
  whole grouped list is visible and every finding is a click away. The
  grouping is shared, so B costs little on top.

## Design

### 1. Grouping (`groups.py`, shared)

A pure function: located findings in, ordered groups out. Non-spelling
stages keep one group each (Spacing and punctuation, Grammar, Repeated
words). Spelling words are sorted into these groups, first match wins, in
this display order:

| Group | Rule (my call; tune against the real book) |
|---|---|
| **Likely typos** | Lower-case-initial, or sentence-initial; not in quotes or bold; aspell has suggestions. Also words that start with a macro name the extractor knows (`bsqentertainment`), noted as "missing \\ before `bsq`?" |
| **Other unknown words** | Anything not caught below |
| **In quotations** | Every use is inside `\say`/`\bsq`/`\enquote` (dialogue, dialect: *vould*, *Ziss*) |
| **Foreign and bold phrases** | Every use is inside bold (`\textbf{au secours}`, `\textbf{Gamla stan}`) |
| **Names** | Capitalised mid-sentence (*Ericsson*, *Kuiper*, *Sohlberg*) |
| **Variants** | A suggestion equals the word ignoring case, hyphens, spaces or accents (*ok*/OK, *heathland*/heath land, *dénouement*/denouement) |

"Inside quotes" uses the curly quote marks the extractor already emits for
`\say` and `\bsq`; "bold" uses `Prose.bold`. Group membership is decided
per word, from all of its uses.

URLs are not prose: the spelling stage skips words inside anything that
matches a URL pattern (`https://…`, `name.co.uk`), so *https* and *uk*
disappear rather than being grouped.

### 2. Terminal report (default)

- Locations are printed relative to the current directory when that is
  shorter (`document.tex:1036:324`). iTerm resolves relative paths against
  the shell's directory, so Cmd-click still reaches `tex-check-open`.
- Spelling is printed group by group, each with a sub-heading and count;
  the other stages as now.
- Each finding is one line (location, word, ×count, suggestions) plus one
  context line, following the shared `scripts/` terminal conventions.
- `--json` gains a `group` field; otherwise unchanged.

### 3. Browser view (`tex-check FILE --web`)

```
$ tex-check document.tex --web
Serving document.tex on http://127.0.0.1:8766/?k=…
Opening your browser…   (ctrl-C to stop)
```

Port 8766 by default (mail-triage has 8765), `--port`, `--no-open`. One
file only; more is an error.

Page layout:

```
┌───────────────────────────┬──────────────────────────────────────────────┐
│ document.tex              │ Likely typos                               9 │
│ checked 14:02 · 217 found │                                              │
│                           │ lyrca            2010:152   → Lycra, Lyra    │
│ Likely typos          9   │ …sed up in capes, in lyrca? Didn't super-…   │
│ Other                31   │          [Open in Texifier] [Add to words]   │
│ In quotations        24   │                                              │
│ Foreign and bold     38   │ Eclesall         1462:180   → Ecclesial, …   │
│ Names                84   │ …ok, further down by Eclesall Woods. I fol…  │
│ Variants             27   │          [Open in Texifier] [Add to words]   │
│ ─────────                 │                                              │
│ Punctuation           2   │                                              │
│ Grammar               2   │                                              │
│                           │                                              │
│ Saved · re-checking in 24s│                                              │
│ [Re-check now]            │                                              │
└───────────────────────────┴──────────────────────────────────────────────┘
```

- A word with several uses shows the first and lists the other lines, each
  clickable to open Texifier there.
- **Open in Texifier** calls the existing `opener.py` logic for that
  file:line:col (factored into a function `open_at(path, line, col)` that
  `main()` also uses). Errors (e.g. Accessibility not granted) appear on the
  page.
- **Two word lists, two buttons.** **Add for this book** appends to
  `tex-check-words.txt` beside the .tex file (names of people in the book,
  dialect, invented words); it travels and syncs with the book and
  survives the folder being moved. **Add everywhere** appends to a personal
  list, `words.txt` at the root of this repository, tracked in git so
  mistaken additions show in the history (good English aspell lacks:
  *heathland*, *matchday*, *cobblestoned*; brands such as *Ericsson*). It is
  found relative to the package source, which works because tex-check is
  an editable install; if that file is absent (a normal install), the
  fallback is `~/.local/share/tex-check/words.txt`. The repository has no
  remote, so nothing leaves the machine. Either creates its file if needed, with a header comment,
  and removes that word's findings from the page at once, without a
  re-check. The terminal and `--json` runs read both lists, so every view
  agrees; `--no-personal-words` leaves the personal list out.
- Light and dark themes follow the system. Hand-written HTML, CSS and JS
  served from `web/static/`; no build step, no external requests.

### 4. Re-checking after a save

The server watches the .tex file's modification time (and both word lists')
once a second. A change starts a 30-second timer; a further change within
those 30 seconds restarts it. When the timer runs out, the checks run again
and the result gets a new version number. **Re-check now** skips the wait.

The page polls a small status endpoint every two seconds: it shows "Saved ·
re-checking in 24s" while waiting, "Checking…" while running, and reloads
the findings when the version changes, keeping the selected group and
scroll position. A check that fails (e.g. aspell missing) is shown on the
page; the previous findings stay visible.

### 5. Security (adapted from mail-triage `web/security.py`)

The page's buttons make the Mac type into Texifier and write a file, so no
other web page may trigger them:

1. Bind `127.0.0.1` only.
2. Strict `Host` check (DNS rebinding).
3. Per-run token: in the opening URL once, then a header on every `/api/`
   request.
4. `Origin` / `Sec-Fetch-Site` checks.
5. Strict CSP (`default-src 'self'`, no frames), `Referrer-Policy:
   no-referrer`, `no-store`.

Routes are a pure request → response function over a session object, so
they are testable without a socket. The API only ever acts on findings by
opaque id from the current version: the browser never sends a path, line
or word list location.

### 6. Code layout

```
src/texcheck/groups.py         grouping (shared)
src/texcheck/report.py         terminal report, now grouped
src/texcheck/web/security.py   adapted from mail-triage
src/texcheck/web/session.py    current findings, versions, word-list writes
src/texcheck/web/watcher.py    mtime polling and the 30 s debounce (injectable clock)
src/texcheck/web/routes.py     pure request → response
src/texcheck/web/server.py     loopback socket and lifetime
src/texcheck/web/static/       index.html, app.css, app.js
```

`cli.py` runs the checks through one function used by the terminal report,
`--json` and the web session, so all three agree.

### 7. Testing

Grouping rules against small synthetic prose (one test per group, plus
order); relative-path printing; URL skipping; routes and security as pure
functions (rejected Host, missing token, wrong Origin); the debounce with a
fake clock (save, save at 20 s, check fires at 50 s); word-list append.
`open_at` is tested through its existing dry-run path. Finally a manual run
against the real book.

## Risks

- **Accessibility permission.** `tex-check-open` works today because iTerm
  has it. The server is started from iTerm, so its `osascript` should be
  attributed to iTerm too; to be confirmed on the first manual run.
- **Grouping heuristics** will misplace some words (a sentence-initial
  name, say). The groups are an aid to reading, not a verdict; tune them
  against the real book.

## Left to the builder

Exact CSS, endpoint names, polling intervals other than the 30-second
debounce, and wording of headings.
