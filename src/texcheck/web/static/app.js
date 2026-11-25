// tex-check's browser view.
//
// The server holds the findings and decides everything; this page draws
// them and sends back opaque ids. It polls /api/status every two seconds and
// redraws when a re-check has produced a new version, keeping the group and
// scroll position, so fixing typos in Texifier never loses your place.
//
// Every use of a word is its own row, because each place needs checking on
// its own: OK clears that one place. Every action is logged beside the book
// and can be undone from the Done view.
//
// Text from the book is put on the page with textContent only, never as
// HTML: a stray "<" in the prose must show as itself.

"use strict";

const TOKEN = document.querySelector('meta[name="token"]').content;
const SPELLING = ["latex", "typos", "other", "quotes", "bold", "names", "variants", "spelling"];
// Spelling's least likely mistakes, shown after every other group.
const LAST = "elsewhere";
const DONE = "__done__";
const POLL_MS = 2000;
const ACTIONS = { ok: "Marked OK", book: "Added for this book", personal: "Added everywhere" };

const state = {
  data: null,        // the last /api/findings
  version: 0,
  group: null,       // key of the group shown, or DONE
  current: 0,        // index of the highlighted row (a use) in the group
  lastError: null,   // so a dismissed check error is not reshown every poll
};

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child === null || child === undefined || child === "") continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

function button(label, onclick, title) {
  return el("button", { type: "button", title: title || label, onclick: (event) => {
    event.stopPropagation();
    onclick();
  } }, label);
}

// ── talking to the server ──────────────────────────────────────────────────

async function api(path, body) {
  const options = { headers: { "X-Tex-Check-Token": TOKEN } };
  if (body !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({ error: "unreadable reply" }));
  if (response.status === 409) {
    showError("The file was re-checked since this was drawn; here is the new list.");
    await loadFindings();
    return null;
  }
  if (!response.ok) {
    showError(payload.error || `request failed (${response.status})`);
    return null;
  }
  return payload;
}

async function loadFindings() {
  const data = await api("/api/findings");
  if (!data) return;
  const scroll = window.scrollY;
  const keep = state.data !== null;
  state.data = data;
  state.version = data.version;
  const keys = data.groups.map((g) => g.key);
  if (!keep || (state.group !== DONE && !keys.includes(state.group))) {
    const first = data.groups.find((g) => SPELLING.includes(g.key) && g.count > 0)
      || data.groups.find((g) => g.count > 0) || data.groups[0];
    state.group = first ? first.key : null;
    state.current = 0;
  }
  await draw();
  if (keep) window.scrollTo(0, scroll);
}

async function poll() {
  try {
    const status = await api("/api/status");
    if (status) {
      drawStatus(status);
      if (status.version !== state.version && status.state !== "checking") await loadFindings();
    }
  } catch {
    $("status").textContent = "Lost touch with tex-check: is it still running?";
  }
  setTimeout(poll, POLL_MS);
}

// ── drawing ────────────────────────────────────────────────────────────────

async function draw() {
  const data = state.data;
  $("file").textContent = data.file;
  const total = data.groups.reduce((sum, g) => sum + g.count, 0);
  $("checked").textContent = `checked ${data.checked_at} · ${total} found`;
  document.title = `${data.file} · tex-check`;
  drawGroups();
  if (state.group === DONE) await drawDone();
  else drawItems();
}

function drawGroups() {
  const nav = $("groups");
  nav.replaceChildren();
  const shown = (g) => g.count > 0 || !SPELLING.includes(g.key) || g.key === "spelling";
  const spelling = state.data.groups.filter((g) => SPELLING.includes(g.key) && shown(g));
  const others = state.data.groups.filter((g) => !SPELLING.includes(g.key) && g.key !== LAST);
  const last = state.data.groups.find((g) => g.key === LAST && (g.count > 0 || g.key === state.group));
  const link = (group) => {
    const classes = ["group-link"];
    if (group.count === 0) classes.push("empty");
    if (group.skipped) classes.push("skipped");
    return el("button", {
      type: "button",
      class: classes.join(" "),
      "aria-current": String(group.key === state.group),
      onclick: () => show(group.key),
    }, el("span", {}, group.title), el("span", { class: "count" }, group.skipped ? "skipped" : group.count));
  };
  if (spelling.length) {
    nav.append(el("p", { class: "section-label" }, "Spelling"));
    spelling.forEach((g) => nav.append(link(g)));
    nav.append(el("hr", { class: "divider" }));
  }
  // Stages split into groups (layout) get a label of their own, like spelling.
  let section = "";
  for (const g of others) {
    if (g.section && g.count === 0) continue;
    if (g.section !== section) {
      if (section) nav.append(el("hr", { class: "divider" }));
      if (g.section) nav.append(el("p", { class: "section-label" }, g.section));
      section = g.section;
    }
    nav.append(link(g));
  }
  if (last) {
    nav.append(el("hr", { class: "divider" }));
    nav.append(el("p", { class: "section-label" }, "Spelling"));
    nav.append(link(last));
  }
  $("done-link").setAttribute("aria-current", String(state.group === DONE));
}

function show(key) {
  state.group = key;
  state.current = 0;
  draw();
  window.scrollTo(0, 0);
}

function currentGroup() {
  return state.data.groups.find((g) => g.key === state.group);
}

// The rows j/k move through: every use of every item in the group, in order.
function rows() {
  const group = currentGroup();
  if (!group) return [];
  return group.items.flatMap((item) => item.uses.map((use) => ({ item, use })));
}

function drawItems() {
  const group = currentGroup();
  const list = $("items");
  list.replaceChildren();
  if (!group) return;
  $("group-title").textContent = group.title;
  $("group-blurb").textContent = group.blurb;
  if (group.skipped) {
    list.append(el("li", { class: "empty-group" }, `Skipped: ${group.skipped}`));
    return;
  }
  if (!group.items.length) {
    list.append(el("li", { class: "empty-group" }, "Nothing here."));
    return;
  }
  state.current = Math.min(state.current, rows().length - 1);
  let index = 0;
  for (const item of group.items) {
    list.append(drawItem(item, index));
    index += item.uses.length;
  }
}

function drawItem(item, firstIndex) {
  const head = el("div", { class: "item-head" });
  if (item.word) {
    head.append(el("span", { class: "word" }, item.word));
    if (item.uses.length > 1) head.append(el("span", { class: "times" }, `×${item.uses.length}`));
    if (item.reason) head.append(el("span", { class: "reason" }, item.reason));
    head.append(drawSuggestions(item.suggestions));
  } else {
    head.append(el("span", { class: "message" }, item.message));
    if (item.note) head.append(el("span", { class: "note" }, item.note));
  }

  const uses = el("ol", { class: "uses" });
  item.uses.forEach((use, i) => uses.append(drawUse(use, firstIndex + i)));

  const li = el("li", { class: "item", "data-id": item.id }, head, uses);
  if (item.word && item.addable) {
    li.append(el("div", { class: "item-actions" },
      button("Add for this book", () => addWord(item, "book"), "every use: add to this book's word list"),
      button("Add everywhere", () => addWord(item, "personal"), "every use: add to your personal word list"),
    ));
  }
  return li;
}

// Each suggestion with the letters that differ from the word marked, and
// the difference said in words ("missing a c"): an extra or missing letter
// is easy to miss by eye.
function drawSuggestions(suggestions) {
  const list = el("ul", { class: "suggestions" });
  if (!suggestions.length) {
    list.append(el("li", { class: "quiet" }, "no suggestions"));
    return list;
  }
  for (const s of suggestions) {
    const word = el("span", { class: "suggestion" });
    for (const [text, changed] of s.parts) word.append(changed ? el("span", { class: "changed" }, text) : text);
    list.append(el("li", {}, "→ ", word, s.difference ? el("span", { class: "difference" }, s.difference) : null));
  }
  return list;
}

function drawUse(use, index) {
  const context = el("p", { class: "context" },
    use.cut_left ? "…" : "", use.before, el("mark", {}, use.hit), use.after,
    use.cut_right ? "…" : "");
  return el("li", {
    class: `use${index === state.current ? " current" : ""}`,
    "data-use": use.id,
    onclick: () => { state.current = index; markCurrent(); },
  },
  context,
  el("span", { class: "where" }, `${state.data.file}:${use.line}:${use.col}`),
  el("span", { class: "use-actions" },
    button("Open in Texifier", () => openUse(use)),
    button("OK", () => markOk(use), "fine here: hide this one place"),
  ));
}

function markCurrent() {
  document.querySelectorAll(".use").forEach((li, i) => li.classList.toggle("current", i === state.current));
}

async function drawDone() {
  const list = $("items");
  $("group-title").textContent = "Done";
  $("group-blurb").textContent = "everything marked OK or added, newest first; kept in tex-check-done.jsonl";
  const reply = await api("/api/done");
  list.replaceChildren();
  if (!reply) return;
  if (!reply.done.length) {
    list.append(el("li", { class: "empty-group" }, "Nothing yet."));
    return;
  }
  for (const entry of reply.done) {
    const what = entry.word || entry.message || entry.text;
    list.append(el("li", { class: `done-entry${entry.undone ? " undone" : ""}` },
      el("span", { class: "when" }, entry.at.slice(11) || entry.at),
      el("span", {}, ACTIONS[entry.action] || entry.action),
      el("span", {}, what, el("span", { class: "where" }, `  line ${entry.line}`)),
      entry.undone ? el("span", { class: "quiet" }, "undone")
        : button("Undo", () => undo(entry), "put this back as it was"),
    ));
  }
}

function drawStatus(status) {
  const line = $("status");
  line.className = "quiet";
  if (status.state === "waiting") {
    line.textContent = `Saved · re-checking in ${status.seconds_left}s`;
    line.className = "waiting";
  } else if (status.state === "checking") {
    // A step running a few seconds says what it is and for how long.
    const slow = status.step && status.step_seconds >= 2;
    line.textContent = slow ? `Checking · ${status.step} · ${status.step_seconds}s` : "Checking…";
  } else {
    line.textContent = "Re-checks 30s after a save";
  }
  $("recheck").disabled = status.state === "checking";
  if (status.error && status.error !== state.lastError) showError(status.error);
  state.lastError = status.error;
}

function showError(text) {
  $("error-text").textContent = text;
  $("error").hidden = false;
}

// ── acting ─────────────────────────────────────────────────────────────────

async function openUse(use) {
  const reply = await api("/api/open", { use: use.id });
  if (reply && reply.error) showError(reply.error);
}

function fadeThenRedraw(nodes) {
  nodes.forEach((node) => node.classList.add("leaving"));
  setTimeout(() => { const y = window.scrollY; draw(); window.scrollTo(0, y); }, nodes.length ? 250 : 0);
}

async function markOk(use) {
  if (!await api("/api/ok", { use: use.id })) return;
  for (const group of state.data.groups) {
    for (const item of group.items) item.uses = item.uses.filter((u) => u.id !== use.id);
    group.items = group.items.filter((item) => item.uses.length);
    group.count = group.items.length;
  }
  fadeThenRedraw([...document.querySelectorAll(`[data-use="${CSS.escape(use.id)}"]`)]);
}

async function addWord(item, scope) {
  const reply = await api("/api/words", { item: item.id, scope });
  if (!reply) return;
  const gone = new Set(reply.removed);
  for (const group of state.data.groups) {
    group.items = group.items.filter((other) => !gone.has(other.id));
    group.count = group.items.length;
  }
  fadeThenRedraw([...$("items").children].filter((li) => gone.has(li.dataset.id)));
}

async function undo(entry) {
  if (!await api("/api/undo", { entry: entry.id })) return;
  await loadFindings();
}

// ── keys ───────────────────────────────────────────────────────────────────

document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey || !state.data || state.group === DONE) return;
  const all = rows();
  if (!all.length) return;
  const row = all[state.current];
  const keys = {
    j: () => { state.current = Math.min(state.current + 1, all.length - 1); },
    k: () => { state.current = Math.max(state.current - 1, 0); },
    o: () => openUse(row.use),
    x: () => markOk(row.use),
    b: () => row.item.word && row.item.addable && addWord(row.item, "book"),
    e: () => row.item.word && row.item.addable && addWord(row.item, "personal"),
  };
  const action = keys[event.key];
  if (!action) return;
  event.preventDefault();
  action();
  if (event.key === "j" || event.key === "k") {
    markCurrent();
    document.querySelectorAll(".use")[state.current].scrollIntoView({ block: "nearest" });
  }
});

$("recheck").addEventListener("click", () => api("/api/recheck", {}));
$("error-close").addEventListener("click", () => { $("error").hidden = true; });
$("done-link").addEventListener("click", () => show(DONE));

loadFindings().then(poll);
