// tex-check's browser view.
//
// The server holds the findings and decides everything; this page draws
// them and sends back opaque ids. It polls /api/status every two seconds and
// redraws when a re-check has produced a new version, keeping the group and
// scroll position, so fixing typos in Texifier never loses your place.
//
// Text from the book is put on the page with textContent only, never as
// HTML: a stray "<" in the prose must show as itself.

"use strict";

const TOKEN = document.querySelector('meta[name="token"]').content;
const SPELLING = ["typos", "other", "quotes", "bold", "names", "variants", "spelling"];
const POLL_MS = 2000;

const state = {
  data: null,        // the last /api/findings
  version: 0,
  group: null,       // key of the group shown
  current: 0,        // index of the highlighted item
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
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
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
  const keepGroup = state.data !== null;
  state.data = data;
  state.version = data.version;
  const keys = data.groups.map((g) => g.key);
  if (!keepGroup || !keys.includes(state.group)) {
    const first = data.groups.find((g) => SPELLING.includes(g.key) && g.count > 0)
      || data.groups.find((g) => g.count > 0) || data.groups[0];
    state.group = first ? first.key : null;
    state.current = 0;
  }
  draw();
  if (keepGroup) window.scrollTo(0, scroll);
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

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function draw() {
  const data = state.data;
  $("file").textContent = data.file;
  const total = data.groups.reduce((sum, g) => sum + g.count, 0);
  $("checked").textContent = `checked ${data.checked_at} · ${total} found`;
  document.title = `${data.file} · tex-check`;
  drawGroups();
  drawItems();
}

function drawGroups() {
  const nav = $("groups");
  nav.replaceChildren();
  const spelling = state.data.groups.filter((g) => SPELLING.includes(g.key));
  const others = state.data.groups.filter((g) => !SPELLING.includes(g.key));
  const link = (group) => {
    const classes = ["group-link"];
    if (group.count === 0) classes.push("empty");
    if (group.skipped) classes.push("skipped");
    return el("button", {
      type: "button",
      class: classes.join(" "),
      "aria-current": String(group.key === state.group),
      onclick: () => { state.group = group.key; state.current = 0; draw(); window.scrollTo(0, 0); },
    }, el("span", {}, group.title), el("span", { class: "count" }, group.skipped ? "skipped" : group.count));
  };
  if (spelling.length) {
    nav.append(el("p", { class: "section-label" }, "Spelling"));
    spelling.forEach((g) => nav.append(link(g)));
    nav.append(el("hr", { class: "divider" }));
  }
  others.forEach((g) => nav.append(link(g)));
}

function currentGroup() {
  return state.data.groups.find((g) => g.key === state.group);
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
  state.current = Math.min(state.current, group.items.length - 1);
  group.items.forEach((item, index) => list.append(drawItem(item, index)));
}

function drawItem(item, index) {
  const first = item.uses[0];
  const head = el("div", { class: "item-head" });
  if (item.word) {
    head.append(el("span", { class: "word" }, item.word));
    if (item.uses.length > 1) head.append(el("span", { class: "times" }, `×${item.uses.length}`));
  } else {
    head.append(el("span", { class: "message" }, item.message));
  }
  head.append(el("span", { class: "where" }, `${state.data.file}:${first.line}:${first.col}`));
  if (item.word) {
    const sugg = el("span", { class: "suggestions" }, "→ ");
    if (item.suggestions.length) {
      item.suggestions.forEach((s, i) => {
        if (i) sugg.append(", ");
        sugg.append(el("b", {}, s));
      });
    } else {
      sugg.append("no suggestions");
    }
    head.append(sugg);
  }
  if (item.note) head.append(el("span", { class: "note" }, item.note));

  const context = el("p", { class: "context" },
    first.cut_left ? "…" : "", first.before, el("mark", {}, first.hit), first.after,
    first.cut_right ? "…" : "");

  const actions = el("div", { class: "actions" },
    el("button", { type: "button", onclick: () => openUse(first) }, "Open in Texifier"));
  if (item.word) {
    actions.append(
      el("button", { type: "button", onclick: () => addWord(item, "book") }, "Add for this book"),
      el("button", { type: "button", onclick: () => addWord(item, "personal") }, "Add everywhere"),
    );
  }
  if (item.uses.length > 1) {
    const also = el("span", { class: "also" }, "also on line ");
    item.uses.slice(1).forEach((use, i) => {
      if (i) also.append(" ");
      also.append(el("button", { type: "button", title: "Open in Texifier", onclick: () => openUse(use) }, use.line));
    });
    actions.append(also);
  }

  return el("li", {
    class: `item${index === state.current ? " current" : ""}`,
    "data-id": item.id,
    onclick: () => { state.current = index; markCurrent(); },
  }, head, context, actions);
}

function markCurrent() {
  [...$("items").children].forEach((li, i) => li.classList.toggle("current", i === state.current));
}

function drawStatus(status) {
  const line = $("status");
  line.className = "quiet";
  if (status.state === "waiting") {
    line.textContent = `Saved · re-checking in ${status.seconds_left}s`;
    line.className = "waiting";
  } else if (status.state === "checking") {
    line.textContent = "Checking…";
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

async function addWord(item, scope) {
  const reply = await api("/api/words", { item: item.id, scope });
  if (!reply) return;
  const gone = new Set(reply.removed);
  for (const group of state.data.groups) {
    group.items = group.items.filter((other) => !gone.has(other.id));
    group.count = group.items.length;
  }
  const leaving = [...$("items").children].filter((li) => gone.has(li.dataset.id));
  leaving.forEach((li) => li.classList.add("leaving"));
  setTimeout(() => { const y = window.scrollY; draw(); window.scrollTo(0, y); }, leaving.length ? 250 : 0);
}

// ── keys ───────────────────────────────────────────────────────────────────

document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey || !state.data) return;
  const group = currentGroup();
  if (!group || !group.items.length) return;
  const item = group.items[state.current];
  const keys = {
    j: () => { state.current = Math.min(state.current + 1, group.items.length - 1); },
    k: () => { state.current = Math.max(state.current - 1, 0); },
    o: () => openUse(item.uses[0]),
    b: () => item.word && addWord(item, "book"),
    e: () => item.word && addWord(item, "personal"),
  };
  const action = keys[event.key];
  if (!action) return;
  event.preventDefault();
  action();
  if (event.key === "j" || event.key === "k") {
    markCurrent();
    $("items").children[state.current].scrollIntoView({ block: "nearest" });
  }
});

$("recheck").addEventListener("click", () => api("/api/recheck", {}));
$("error-close").addEventListener("click", () => { $("error").hidden = true; });

loadFindings().then(poll);
