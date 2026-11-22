# Grouped findings and browser view: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sort findings into groups (likely typos first) in the terminal and in
a new local browser view, where any finding opens Texifier at its line and any
word can be added to the book's or the personal word list. The view re-checks
30 seconds after the last save.

**Architecture:** A shared `check_file` runs the stages and `group_findings`
sorts the results. The terminal report, `--json` and the web session all use
both, so they agree. The web layer is mail-triage's pattern on a small scale:
stdlib `http.server` on loopback, a token, pure `Router.handle(Request) ->
Response`, and hand-written static files.

**Tech Stack:** Python 3.12+ stdlib only, aspell, pytest; HTML/CSS/JS with no
build step.

**Spec:** `docs/superpowers/specs/2026-11-22-grouped-report-and-web-view-design.md`

## Global Constraints

- No runtime dependencies: `dependencies = []` in `pyproject.toml` stays empty.
- The server binds `127.0.0.1` only. The default port is `8766`, with `--port` and `--no-open`.
- The page makes no external requests (no CDN, fonts or analytics). CSP is `default-src 'self'` with `frame-src 'none'`.
- The re-check delay is 30 seconds after the last save, and every further save restarts it.
- The book word list is `tex-check-words.txt` beside the .tex file. The personal list is `words.txt` at the repo root, with `~/.local/share/tex-check/words.txt` (`places.data_dir()`) as the fallback.
- Terminal output follows `scripts/CLAUDE.md`: measure on plain text and style afterwards. `--json` and piped output stay plain.
- British English in all user-facing text.
- Work on branch `feature/grouped-web-view`, never on `main`.

## Review Focus

1. **A word added to a list while a re-check is waiting** must not come back once the re-check finishes. The re-check reads the lists afresh (Task 8 test `test_recheck_reads_new_words`).
2. **The .tex file is saved half-written or deleted during the 30 seconds.** The re-check reports an error on the page and keeps the previous findings (Task 8 test `test_failed_recheck_keeps_findings`).
3. **Stale ids after a re-check.** An `/api/open` with an id from the old version gets 409 with "re-checked; reload", never a wrong line (Task 9 test `test_stale_id_is_refused`).
4. **A word with an apostrophe or curly quote** (*there'd*, *Sohlberg’s*) is written to the word list normalised (`'`), only once, and the spelling stage accepts it afterwards (Task 2 test `test_append_word_normalises_and_dedupes`).
5. **The file lies outside the current directory** (as in the real run): the terminal shows the absolute path, not `../../..`, so Cmd-click still works (Task 5 test `test_display_path_outside_cwd_is_absolute`).

---

### Task 1: Skip URLs in the spelling stage

**Files:**
- Modify: `src/texcheck/checks/spelling.py` (`candidates`)
- Test: `tests/test_checks.py`

**Interfaces:**
- Produces: `spelling.URL: re.Pattern` matches `https?://\S+`, `www\.\S+` and bare domains like `name.co.uk` (`\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|uk|io|fi|de|fr)\b`, with an optional trailing path).

- [ ] **Step 1: Write the failing tests**

```python
def test_urls_are_not_spell_checked():
    words = messages(spelling, r"See (https://youloveprint.co.uk) and elmandash.co.uk today.")
    assert words == []

def test_words_beside_urls_still_are():
    assert messages(spelling, r"A lyrca at https://example.com/x.") == ["lyrca"]
```
(Mark both `@pytest.mark.skipif(not shutil.which("aspell"), ...)`, as the existing spelling tests do.)

- [ ] **Step 2: Run** `uv run pytest tests/test_checks.py -k url -v`. Expected: FAIL, with `https`, `uk` and others reported.
- [ ] **Step 3: Implement.** In `candidates`, collect the URL spans of `prose.text` once, and skip any match that falls inside one.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit** with `git checkout -b feature/grouped-web-view` (first task only), then `git commit -am "Skip URLs in the spelling stage"`.

### Task 2: Word lists, personal and per book

**Files:**
- Create: `src/texcheck/wordlists.py`, `words.txt` (repo root: header comment only)
- Modify: `src/texcheck/checks/spelling.py` (`load_wordlists` moves to `wordlists.load`; spelling imports it), `src/texcheck/cli.py` (reads the personal list; `--no-personal-words`)
- Test: `tests/test_wordlists.py`

**Interfaces:**
- Produces:
  - `BOOK_NAME = "tex-check-words.txt"` (moved from `cli.WORDLIST_NAME`)
  - `book_file(tex: Path) -> Path`
  - `personal_file() -> Path`: returns `Path(__file__).resolve().parents[2] / "words.txt"` if `pyproject.toml` sits beside it, else `places.data_dir() / "words.txt"`.
  - `load(paths: list[Path]) -> set[str]`: lower-cased and normalised, as now. Missing files are skipped.
  - `append_word(path: Path, word: str) -> bool`: creates the file and its parents with the header `# tex-check word list: one word per line, '#' starts a comment`, normalises `’` to `'`, and returns False (writing nothing) if the word is already there, case-insensitively.

- [ ] **Step 1: Write the failing tests**

```python
def test_append_word_creates_with_header(tmp_path):
    f = tmp_path / "sub" / "w.txt"
    assert append_word(f, "Sohlberg") is True
    assert f.read_text().splitlines() == [HEADER, "Sohlberg"]

def test_append_word_normalises_and_dedupes(tmp_path):
    f = tmp_path / "w.txt"
    append_word(f, "Sohlberg’s")
    assert append_word(f, "sohlberg's") is False
    assert load([f]) == {"sohlberg's"}

def test_personal_file_is_in_the_repo():
    assert personal_file() == Path(__file__).resolve().parents[1] / "words.txt"

def test_cli_reads_personal_list(tmp_path, monkeypatch): ...
    # monkeypatch wordlists.personal_file to a tmp file holding "lyrca";
    # main([tex with "lyrca", "--only", "spell", "--json"]) reports nothing,
    # and with --no-personal-words reports "lyrca".
```

- [ ] **Step 2: Run** `uv run pytest tests/test_wordlists.py -v`. Expected: FAIL (no module).
- [ ] **Step 3: Implement** `wordlists.py`. Create `words.txt` holding the header line. In `cli.py`, `Settings.wordlists` becomes book list + personal list (unless `--no-personal-words`) + `--words`, keeping only files that exist. Update the epilog's word-list paragraph.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit** `git add -A && git commit -m "Add a personal word list beside the per-book one"`.

### Task 3: One shared run: `check_file` and `Located`

**Files:**
- Create: `src/texcheck/run.py`
- Modify: `src/texcheck/report.py` (`Located` moves out; imports it), `src/texcheck/cli.py` (per-file loop calls `check_file`)
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: `wordlists.book_file`, `wordlists.personal_file`
- Produces:
  - `@dataclass(frozen=True) class Options: dictionary="en_GB-ise", extra_wordlists: tuple[Path, ...]=(), spell_bold=False, spell_capitals=False, personal_words=True`
  - `class Located` (unchanged, moved from report.py)
  - `@dataclass class Run: path: Path; source: Source; prose: Prose; results: list[tuple[module, list[Finding] | str]]; stats: dict`
  - `check_file(path: Path, stages: list, options: Options, gazetteer: set[str] | None) -> Run`: reads the file (utf-8, falling back to latin-1, as `cli.read` does), builds `Settings` with the word lists read afresh on every call, and turns `SpellerMissing` into the string outcome.

- [ ] **Step 1: Write the failing test.** `test_check_file_matches_cli`: write a tmp .tex with "the the" and "lyrca". `check_file(...)` gives one repeats finding and one spelling finding. A `tex-check-words.txt` holding "lyrca" written afterwards is honoured by a second `check_file` call (the lists are read per call).
- [ ] **Step 2: Run** `uv run pytest tests/test_run.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement**, then make `cli.main` use `check_file` with an `Options` built from args. Its behaviour and exit codes don't change.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all pass, including the existing CLI tests.
- [ ] **Step 5: Commit** `"Share one check run between the CLI and later views"`.

### Task 4: Grouping

**Files:**
- Create: `src/texcheck/groups.py`
- Modify: `src/texcheck/prose.py` (export `KNOWN_COMMANDS: frozenset[str]`, the union of keys in `DROP_ARGS`, `HEADINGS`, `NOTES`, `BREAKS`, `BOLD`, `QUOTES`, `MACROS`)
- Test: `tests/test_groups.py`

**Interfaces:**
- Consumes: `Run`, `Located`
- Produces:
  - `@dataclass class Item: key: str; stage: str; word: str | None; message: str; note: str; suggestions: list[str]; uses: list[Located]`. `key` is `"spelling:<word>"` or `"<stage>:<prose start>"`.
  - `@dataclass class Group: key: str; title: str; blurb: str; items: list[Item]; skipped: str | None = None`
  - `SPELLING_GROUPS`: ordered `(key, title, blurb)` with keys `typos, other, quotes, bold, names, variants` and titles "Likely typos", "Other unknown words", "In quotations", "Foreign and bold phrases", "Names", "Variants".
  - `group_findings(run: Run) -> list[Group]`: stages in run order. Spelling is replaced by its non-empty sub-groups in `SPELLING_GROUPS` order, or by one empty `spelling` group if it found nothing. Items within a group follow their first use.
  - `classify(word: str, uses: list[Located], suggestions: list[str], prose: Prose, source: Source) -> tuple[str, str]`: returns (group key, note).

Rules are **evaluated** in this order (it differs from the display order); the first match wins:

1. **Macro slip → `typos`**, with the note ``missing \ before \bsq?``. The source text of a use contains `{` or `}` and the word starts with a name in `KNOWN_COMMANDS`.
2. **`variants`**: some suggestion `s` has `fold(s) == fold(word)`, where `fold` lower-cases, drops `-` and spaces, and strips accents (NFKD, combining marks removed).
3. **`quotes`**: every use lies inside `“…”` or `‘…’` in `prose.text`, without crossing a paragraph break.
4. **`bold`**: every use has `prose.bold[start]` set.
5. **`names`**: the word is capitalised and at least one use is not at the start of a sentence (the previous non-space prose character is not `.`, `!`, `?`, a newline, or the start).
6. **`typos`**: the word starts lower-case and aspell offered suggestions.
7. **`other`**: everything else.

- [ ] **Step 1: Write the failing tests**, one per rule, using `check_file` on small tmp .tex bodies (skip if aspell is missing):
  - `test_macro_slip_is_a_typo`: `"briefly bsq{entertainment} for"` gives `typos` and a note containing `\bsq`
  - `test_case_only_difference_is_a_variant`: `"it was ok then"` gives `variants`
  - `test_split_word_is_a_variant`: `"the heathland in winter"` gives `variants`
  - `test_dialogue_goes_to_quotes`: `r"\say{That vos a pity} he said"` gives `vos` → `quotes`
  - `test_bold_foreign_phrase`: `r"shouting \textbf{au secours} then"` gives `secours` → `bold`
  - `test_mid_sentence_capital_is_a_name`: `"working at Ericsson, we"` gives `names`
  - `test_lowercase_with_suggestions_is_a_typo`: `"capes, in lyrca? Didn't"` gives `typos`
  - `test_display_order_and_counts`: one word of each kind; the group keys come out in the order `repeats, punctuation, typos, other, quotes, bold, names, variants, grammar`, leaving out empty spelling sub-groups
  - `test_word_uses_are_one_item`: "lyrca … lyrca" gives one item with two uses
- [ ] **Step 2: Run** `uv run pytest tests/test_groups.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `groups.py` and `KNOWN_COMMANDS`.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit** `"Sort findings into groups, likely typos first"`.

### Task 5: Grouped terminal report and shorter paths

**Files:**
- Modify: `src/texcheck/report.py`, `src/texcheck/cli.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `group_findings`, `Run`
- Produces:
  - `display_path(path: Path, cwd: Path) -> str`: the path relative to `cwd` when the file lies under `cwd`, otherwise the absolute path.
  - `print_report(run: Run, groups: list[Group], style: Style, cwd: Path) -> None`
  - `as_json(run, groups) -> list[dict]`: as now, plus `"group": <group key>`

Layout: the stage heading as now. Spelling becomes a "Spelling" heading whose sub-headings are bold group titles, each with a dim blurb and a count, indented two spaces. Items are laid out as now, with `display_path` in place of the full path. The place-names line stays under the Spelling heading. The summary lists each spelling sub-group, indented under Spelling.

- [ ] **Step 1: Write the failing tests**
  - `test_display_path_inside_cwd_is_relative`: `display_path(tmp/"a/doc.tex", tmp) == "a/doc.tex"`
  - `test_display_path_outside_cwd_is_absolute`: `display_path(Path("/x/doc.tex"), tmp) == "/x/doc.tex"`
  - `test_report_shows_group_titles_in_order`: capture `print_report` output (colour off). "Likely typos" appears before "Names".
  - `test_json_has_group`: every spelling item carries `group`
- [ ] **Step 2: Run** `uv run pytest tests/test_report.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** `cli.main` passes `Path.cwd()`.
- [ ] **Step 4: Run** `uv run pytest -v`, then run `uv run tex-check path/to/book/document.tex` from that folder and read the output. Expected: the tests pass; the locations read `document.tex:…`; Likely typos comes first.
- [ ] **Step 5: Commit** `"Group the terminal report and shorten locations"`.

### Task 6: `open_at` in the opener

**Files:**
- Modify: `src/texcheck/opener.py`
- Test: `tests/test_opener.py`

**Interfaces:**
- Produces: `open_at(path: Path, line: int, col: int, app: str = APP, run=subprocess.run) -> str | None`. It returns None on success or a one-line error, including the Accessibility hint when the error contains "assistive access" or "-1719". `main()` calls it and prints any error to stderr (exit 1), as now.

- [ ] **Step 1: Write the failing tests** with a fake `run` that records argv:
  - `test_open_at_opens_then_finds`: the first call is `open -a Texifier <path>`, and the second is `osascript` with the unique phrase.
  - `test_open_at_reports_accessibility`: the fake osascript fails with "-1719". The result contains "Accessibility".
- [ ] **Step 2: Run** `uv run pytest tests/test_opener.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** by moving the body of `main` into `open_at`.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit** `"Let the opener be called as a function"`.

### Task 7: Web security

**Files:**
- Create: `src/texcheck/web/__init__.py`, `src/texcheck/web/security.py`
- Test: `tests/test_web_security.py`

**Interfaces:**
- Produces, adapted from `../mail-triage/src/mail_triage/web/security.py`:
  - `Request`, `Response` (with `Response.json`), `TokenGate`, `session_cookie(token)`, `check_request(request, gate, port) -> Response | None`, `SECURITY_HEADERS`
  - Changes: the cookie is `tex_check_session`; the API header is `X-Tex-Check-Token`; CSP `frame-src 'none'`. Rewrite the module docstring for this threat (the page can type into Texifier and write word lists).

- [ ] **Step 1: Write the failing tests** (port 8766):
  - `test_foreign_host_refused`: `Host: evil.example:8766` gives 403
  - `test_api_needs_header_token`: a cookie alone on `/api/findings` gives 403; with the header it is None
  - `test_cross_origin_refused`: `Origin: http://evil.example` gives 403
  - `test_url_token_works_once`: `/?k=T` is allowed, and refused the second time
- [ ] **Step 2: Run** `uv run pytest tests/test_web_security.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** by copying and adapting.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit** `"Add loopback web security, adapted from mail-triage"`.

### Task 8: Session and the debounced watcher

**Files:**
- Create: `src/texcheck/web/session.py`, `src/texcheck/web/watcher.py`
- Test: `tests/test_web_session.py`

**Interfaces:**
- Consumes: `check_file`, `Options`, `group_findings`, `snippet` (report.py), `open_at`, `wordlists.append_word`, `book_file`, `personal_file`
- Produces:
  - `class Debouncer(delay: float = 30.0, clock=time.monotonic)` with `touch()`, `due() -> bool` (True once, when `delay` has passed since the last `touch`), `seconds_left() -> float | None`, `cancel()`
  - `class Watcher(paths: Callable[[], list[Path]], debouncer: Debouncer, on_due: Callable[[], None], interval: float = 1.0)`: a daemon thread. `poll()` (one step, for tests) compares the mtimes (missing counts as None), calls `debouncer.touch()` on a change, and calls `on_due()` when `due()`. `rebaseline()` records the current mtimes without touching. `start()` / `stop()`.
  - `class Session(path, stages, options, gazetteer, opener=open_at, clock=time.monotonic)`: holds the current `Run`, its groups and `version: int` (starting at 1). It has a `threading.Lock` and the methods:
    - `findings() -> dict`: `{version, file, checked_at, groups: [{key, title, blurb, skipped, count, items: [{id, word, message, note, suggestions, uses: [{id, line, col, before, hit, after}]}]}]}`. Ids are `f"{version}.{n}"`; `before/hit/after` are plain strings from the same window as `snippet`.
    - `status() -> dict`: `{version, state: "idle" | "waiting" | "checking", seconds_left, error}`
    - `open(use_id) -> str | None`: raises `StaleId` for a different version or an unknown id
    - `add_word(item_id, scope: "book" | "personal") -> list[str]`: appends the word and drops every item with that word (in any group) from the current groups, so `findings()` no longer shows it. Returns the removed item ids, then calls `watcher.rebaseline()` so the write is not taken for a save.
    - `recheck()`: runs `check_file`. On success it bumps the version and clears the error; on an exception it sets `error` and keeps the findings.

- [ ] **Step 1: Write the failing tests**, with a fake clock and tmp files:
  - `test_debounce_restarts_on_second_save`: touch at 0, touch at 20; `due()` is False at 49 and True at 50, then False again
  - `test_watcher_sees_save_and_fires`: change the .tex mtime, `poll()`; advance the clock by 30; `poll()` calls `on_due` once
  - `test_add_word_removes_item_and_writes_book_list`: "lyrca" goes to `tex-check-words.txt`, and `findings()` has no lyrca
  - `test_add_word_is_not_a_save`: after `add_word`, `poll()` does not touch
  - `test_recheck_reads_new_words`: add a word to the personal list (patched to tmp), then `recheck()`; the word stays gone and the version goes up
  - `test_failed_recheck_keeps_findings`: delete the .tex, then `recheck()`; `status()["error"]` is set and the same findings and version remain
  - `test_stale_id_raises`: `open("1.0")` after `recheck()` raises `StaleId`
- [ ] **Step 2: Run** `uv run pytest tests/test_web_session.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Session owns its Watcher, created with `paths=lambda: [path, book_file(path), personal_file()]` and `on_due=self.recheck`.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit** `"Add the web session and the 30-second re-check"`.

### Task 9: Routes

**Files:**
- Create: `src/texcheck/web/routes.py`
- Test: `tests/test_web_routes.py`

**Interfaces:**
- Consumes: `Session`, `Request`, `Response`, `TokenGate`, `check_request`
- Produces: `class Router(session: Session, token: str, port: int)` with `handle(request) -> Response` and `last_request: float`. Routes:
  - `GET /` serves `static/index.html`, with `{{TOKEN}}` replaced in its `<meta name="token">`; sets `session_cookie`
  - `GET /static/<name>` serves only names in the static folder (no `..`), with content types for .css and .js
  - `GET /api/findings` returns `session.findings()`; `GET /api/status` returns `session.status()`
  - `POST /api/open {"use": id}` returns `{"ok": true}`, `{"error": msg}` with 200, or 409 `{"error": "re-checked; reload"}` on `StaleId`
  - `POST /api/words {"item": id, "scope": "book"|"personal"}` returns `{"removed": [...]}`; a bad scope gives 400
  - `POST /api/recheck` returns `{"ok": true}` (it runs `session.recheck` in a thread)
  - Every response carries `SECURITY_HEADERS`; everything else gives 404

- [ ] **Step 1: Write the failing tests**, using a Session with a fake opener:
  - `test_index_embeds_token`
  - `test_static_refuses_traversal`: `/static/../routes.py` gives 404
  - `test_open_calls_opener_with_line_and_col`
  - `test_stale_id_is_refused`: 409
  - `test_words_bad_scope_is_400`
  - `test_api_without_token_is_403`
- [ ] **Step 2: Run** `uv run pytest tests/test_web_routes.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement**, with a placeholder `index.html` holding the meta tag (Task 11 fills it).
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit** `"Add the web routes"`.

### Task 10: Server and `--web`

**Files:**
- Create: `src/texcheck/web/server.py`
- Modify: `src/texcheck/cli.py` (`--web`, `--port` default 8766, `--no-open`)
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `Router`, `Session`
- Produces: `serve(router, port=8766, open_browser=True, idle_timeout=1800.0, on_ready=None) -> None`, adapted from mail-triage's `serve` without the quit route. It runs until Ctrl-C, or 30 minutes with no request (the page polls every 2 s, so this only fires once the tab is closed). It starts and stops the session's watcher.

CLI: `--web` with more than one file is an error (exit 2, "--web takes one file"). It prints `Serving document.tex on http://127.0.0.1:PORT/?k=…`, then `Opening your browser…   (ctrl-C to stop)` in the house style.

- [ ] **Step 1: Write the failing test.** `test_server_answers_on_loopback`: `serve` in a thread on port 0 with `open_browser=False` and an `on_ready` that captures the URL. `urllib` GETs the URL and receives 200 HTML; `/api/findings` with the header token returns JSON with `version == 1`. Then shut it down.
- [ ] **Step 2: Run** `uv run pytest tests/test_web_server.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit** `"Serve the browser view with tex-check --web"`.

### Task 11: The page

**Files:**
- Create/replace: `src/texcheck/web/static/index.html`, `app.css`, `app.js`
- Test: manual (below); `test_web_routes.py` already covers serving.

The layout follows the spec's sketch:
- **Sidebar:** the file name, "checked HH:MM · N found", the groups with their counts (spelling sub-groups first, then a rule, then the other stages), and the re-check status line with a **Re-check now** button.
- **Main pane:** the selected group's items. Each item shows the word, the first location, the suggestions, and the context with the hit highlighted. Its buttons are **Open in Texifier**, **Add for this book** and **Add everywhere** (word items only). For words with several uses, the other line numbers are links that open Texifier at that use.
- **Behaviour:** poll `/api/status` every 2 s. When the version changes, refetch the findings and keep the selected group and scroll position. A word added is removed in place and its counts updated. Errors show in a dismissable bar. `j`/`k` move between items, `o` opens the current one.
- **Look:** system font stack and light/dark themes from `prefers-color-scheme`. The token comes from the meta tag and is sent as `X-Tex-Check-Token`.

- [ ] **Step 1: Write the three files.**
- [ ] **Step 2: Manual check.** From the book folder, run `uv run tex-check document.tex --web`. Click Open in Texifier on a Likely typo: Texifier comes forward with the word selected. If it opens without selecting, Accessibility is not inherited; record that in CLAUDE.md and grant it to the right process. Next, add a test word for this book: it vanishes, and `tex-check-words.txt` gains it. Then save the .tex twice, 10 s apart: the countdown restarts, and the findings refresh 30 s after the second save.
- [ ] **Step 3: Commit** `"Add the browser view's page"`.

### Task 12: Documentation

**Files:**
- Modify: `CLAUDE.md` (groups, the two word lists, `--web` and its security, the Accessibility finding from Task 11), `README.md` (usage)

- [ ] **Step 1: Update both files**, then run `uv run pytest -v`. Expected: all pass.
- [ ] **Step 2: Commit** `"Document grouping, word lists and the browser view"`.
