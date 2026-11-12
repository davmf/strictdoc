/*
 * The SysML workspace screen (strictdoc/features/sysml_workspace).
 *
 * - A click on an entry of the tree, of a table, of the relations or of a
 *   diagram box (links to /workspace?item=<ID>) loads the panes of the
 *   entry from /workspace/panes and swaps them in, without reloading the
 *   page. The browser history follows.
 * - The toggles of the tree expand and collapse an entry. The expanded
 *   entries are kept in localStorage.
 * - The filter box shows the entries whose ID or title contains the text,
 *   and their parents.
 * - A create form ignores the "reload" message of the server's websocket
 *   (websocket.jinja.html) once it is submitted: the server sends it while
 *   it answers the form, and reloading the page would cancel the redirect
 *   to the new entry.
 *
 * - The view editor previews the view as it is typed: the server writes the
 *   view file for the fields (/workspace/view_source, nothing is saved), and
 *   the diagram of the view is drawn with that text (drawWithFile()).
 *
 * Without the script, every link loads the whole screen.
 */

import { drawWithFile } from "./sysml-diagrams.js";

const WORKSPACE_PATH = "/workspace";
const PANES_URL = "/workspace/panes";
const EXPANDED_KEY = "strictdoc.sysmlWorkspace.expanded";
const VIEW_SOURCE_URL = "/workspace/view_source";
const PREVIEW_DELAY_MS = 500;

function tree() {
  return document.querySelector(".sysml-ws-tree");
}

function treeEntry(entryId) {
  for (const entry_ of document.querySelectorAll(".sysml-ws-tree-entry")) {
    if (entry_.dataset.entryId === entryId) {
      return entry_;
    }
  }
  return null;
}

function savedExpanded() {
  try {
    return new Set(JSON.parse(localStorage.getItem(EXPANDED_KEY) || "[]"));
  } catch (error) {
    return new Set();
  }
}

function saveExpanded() {
  const expanded = [];
  for (const entry_ of document.querySelectorAll(
    '.sysml-ws-tree-entry[aria-expanded="true"]'
  )) {
    expanded.push(entry_.dataset.entryId);
  }
  try {
    localStorage.setItem(EXPANDED_KEY, JSON.stringify(expanded));
  } catch (error) {
    // Private mode: the tree is not remembered.
  }
}

function restoreExpanded() {
  for (const entryId_ of savedExpanded()) {
    const entry = treeEntry(entryId_);
    if (entry !== null && entry.hasAttribute("aria-expanded")) {
      entry.setAttribute("aria-expanded", "true");
    }
  }
}

function select(entryId) {
  for (const link_ of document.querySelectorAll(".sysml-ws-selected")) {
    link_.classList.remove("sysml-ws-selected");
  }
  const entry = treeEntry(entryId);
  if (entry === null) {
    return;
  }
  const link = entry.querySelector(":scope > .sysml-ws-row > .sysml-ws-link");
  link.classList.add("sysml-ws-selected");
  for (
    let parent_ = entry.parentElement.closest(".sysml-ws-tree-entry");
    parent_ !== null;
    parent_ = parent_.parentElement.closest(".sysml-ws-tree-entry")
  ) {
    parent_.setAttribute("aria-expanded", "true");
  }
  link.scrollIntoView({ block: "nearest" });
}

// The entry ID of a link to the workspace, or null.
function linkedEntryId(link) {
  const href = link.getAttribute("href") || link.getAttribute("xlink:href");
  if (href === null) {
    return null;
  }
  const url = new URL(href, window.location.href);
  if (url.origin !== window.location.origin || url.pathname !== WORKSPACE_PATH) {
    return null;
  }
  return url.searchParams.get("item") || "";
}

async function show(entryId, pushState) {
  const main = document.getElementById("sysml-ws-main");
  const side = document.getElementById("sysml-ws-side");
  main.setAttribute("aria-busy", "true");
  let panes;
  try {
    const response = await fetch(
      `${PANES_URL}?item=${encodeURIComponent(entryId)}`,
      { cache: "no-store" }
    );
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    panes = await response.json();
  } catch (error) {
    // Let the server render the whole screen, with its error page.
    window.location.href = `${WORKSPACE_PATH}?item=${encodeURIComponent(entryId)}`;
    return;
  }
  main.innerHTML = panes.main;
  side.innerHTML = panes.side;
  main.removeAttribute("aria-busy");
  main.scrollTop = 0;
  document.title = panes.title;
  select(panes.id);
  if (pushState) {
    const url = entryId === "" ? WORKSPACE_PATH : `${WORKSPACE_PATH}?item=${encodeURIComponent(entryId)}`;
    history.pushState({ entryId }, "", url);
  }
}

function onClick(event) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey ||
      event.ctrlKey || event.shiftKey || event.altKey) {
    return;
  }
  const addExpose = event.target.closest('[data-action="add-expose"]');
  if (addExpose !== null) {
    addExposeLine(addExpose.closest("form"));
    return;
  }
  const toggle = event.target.closest(".sysml-ws-toggle");
  if (toggle !== null) {
    const entry = toggle.closest(".sysml-ws-tree-entry");
    entry.setAttribute(
      "aria-expanded",
      entry.getAttribute("aria-expanded") === "true" ? "false" : "true"
    );
    saveExpanded();
    return;
  }
  const link = event.target.closest("a");
  if (link === null || link.target === "_blank") {
    return;
  }
  const entryId = linkedEntryId(link);
  if (entryId === null) {
    return;
  }
  event.preventDefault();
  show(entryId, true);
}

function filter(text) {
  const words = text.toLowerCase().split(/\s+/).filter((word_) => word_ !== "");
  const root = tree().querySelector(".sysml-ws-tree-list");
  const visit = (entry) => {
    let visible = words.every((word_) => entry.dataset.search.includes(word_));
    for (const child_ of entry.querySelectorAll(
      ":scope > ul > .sysml-ws-tree-entry"
    )) {
      if (visit(child_)) {
        visible = true;
      }
    }
    entry.hidden = words.length > 0 && !visible;
    entry.classList.toggle("sysml-ws-filtered", words.length > 0);
    return visible;
  };
  for (const entry_ of root.querySelectorAll(":scope > .sysml-ws-tree-entry")) {
    visit(entry_);
  }
}

restoreExpanded();
const selected = document.querySelector(".sysml-ws-selected");
if (selected !== null) {
  select(selected.dataset.entryId);
}
document.addEventListener("click", onClick);
document.getElementById("sysml-ws-filter").addEventListener("input", (event) => {
  filter(event.target.value);
});
// The view editor.

let previewTimer = null;
let previewRun = 0;

function addExposeLine(form) {
  const input = form.querySelector('[data-testid="sysml-workspace-view-add-expose"]');
  const value = input.value.trim();
  if (value === "") {
    return;
  }
  const exposes = form.elements.exposes;
  exposes.value = exposes.value.replace(/\s*$/, "");
  exposes.value += (exposes.value === "" ? "" : "\n") + value;
  input.value = "";
  schedulePreview(form);
}

function schedulePreview(form) {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => preview(form), PREVIEW_DELAY_MS);
}

async function preview(form) {
  const run = ++previewRun;
  const state = form.querySelector(".sysml-ws-preview-state");
  const placeholder = document.querySelector(
    '#sysml-ws-main [data-testid="sysml-workspace-diagram"]'
  );
  if (placeholder === null) {
    return;
  }
  state.textContent = "Drawing the preview...";
  state.dataset.state = "busy";
  try {
    const response = await fetch(VIEW_SOURCE_URL, {
      method: "POST",
      body: new FormData(form),
      cache: "no-store",
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    const svg = await drawWithFile(
      placeholder.dataset.sysmlOptions,
      result.name,
      result.text
    );
    if (run !== previewRun) {
      return;
    }
    placeholder.innerHTML = svg;
    placeholder.dataset.sysmlState = "drawn";
    placeholder.dataset.sysmlPreview = "true";
    state.textContent = "Preview: not saved yet.";
    state.dataset.state = "preview";
  } catch (error) {
    if (run !== previewRun) {
      return;
    }
    state.textContent = error && error.message ? error.message : String(error);
    state.dataset.state = "error";
  }
}

document.addEventListener("input", (event) => {
  const form = event.target.closest(".sysml-ws-view-form");
  if (form !== null && event.target.dataset.testid !== "sysml-workspace-view-add-expose") {
    schedulePreview(form);
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" &&
      event.target.dataset.testid === "sysml-workspace-view-add-expose") {
    event.preventDefault();
    addExposeLine(event.target.closest("form"));
  }
});
document.addEventListener("submit", () => {
  if (window.ws instanceof WebSocket) {
    window.ws.onmessage = null;
  }
});
window.addEventListener("popstate", () => {
  show(new URLSearchParams(window.location.search).get("item") || "", false);
});
