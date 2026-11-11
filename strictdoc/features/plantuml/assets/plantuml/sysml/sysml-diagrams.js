/*
 * Draws the SysML diagrams of a StrictDoc page with the PlantUML engine
 * (TeaVM build, MIT license).
 *
 * - A placeholder <div class="sysml-diagram" data-sysml-options="...">
 *   holds the options of a PlantUML !include_sysml directive. The SysML
 *   reader puts one at the top of each SysML document (see
 *   strictdoc/backend/sysml/diagram.py).
 * - On a page with such a document placeholder, each item (an
 *   <sdoc-anchor data-uid>) that is a diagram gets one: a state machine or
 *   another profile root (root=<UID>), a saved view (diagram=<UID>). The
 *   other items get a "Traces" button that draws their trace diagram
 *   (view=requirements focus=<UID>).
 *
 * A diagram fits the width of the page. A click on it, outside its links,
 * shows it at its full size, with a scroll bar.
 *
 * The SysML files come from /actions/sysml/model_files, once per page and
 * again after a save. Placeholders are drawn when they scroll into view,
 * one at a time. A MutationObserver finds the placeholders of nodes that
 * arrive later (lazy document chunks, nodes updated after a save).
 */

const BASE_URL = new URL(".", import.meta.url);
const MODEL_FILES_URL = "/actions/sysml/model_files";
const NODE_LINKS = "links=/?a={id}";

let enginePromise = null;
let modelPromise = null;
let drawQueue = Promise.resolve();

function loadScript(url) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = url;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Could not load ${url}`));
    document.head.appendChild(script);
  });
}

function engine() {
  if (enginePromise === null) {
    enginePromise = (async () => {
      if (typeof window.Viz === "undefined") {
        await loadScript(new URL("../viz-global.js", BASE_URL).href);
      }
      if (typeof window.ELK === "undefined") {
        await loadScript(new URL("elk.bundled.js", BASE_URL).href);
      }
      return import(new URL("plantuml-mit.js", BASE_URL).href);
    })();
  }
  return enginePromise;
}

// The files of the project and what they hold: { names, texts, roots,
// diagrams }. roots maps an item UID to its profile; diagrams is the set of
// the UIDs of the saved views.
function model() {
  if (modelPromise === null) {
    modelPromise = (async () => {
      const response = await fetch(MODEL_FILES_URL, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`${MODEL_FILES_URL}: HTTP ${response.status}`);
      }
      const files = (await response.json()).files;
      const names = files.map((file_) => file_.name);
      const texts = files.map((file_) => file_.text);
      const plantuml = await engine();
      const description = await new Promise((resolve, reject) => {
        plantuml.sysmlDescribe(names, texts, [], resolve, reject);
      }).then(JSON.parse, () => ({ roots: [], diagrams: [] }));
      const roots = new Map();
      for (const root_ of description.roots) {
        if (root_.id !== null && root_.id !== undefined) {
          roots.set(root_.id, root_.profile);
        }
      }
      const diagrams = new Set(
        (description.diagrams || []).map((diagram_) => diagram_.id)
      );
      return { names, texts, roots, diagrams };
    })();
  }
  return modelPromise;
}

// "view=requirements root=\"A b\"" -> ["view=requirements", "root=A b"]
function optionWords(options) {
  const words = [];
  const pattern = /(\S+?)=("([^"]*)"|\S*)/g;
  let match;
  while ((match = pattern.exec(options)) !== null) {
    words.push(`${match[1]}=${match[3] !== undefined ? match[3] : match[2]}`);
  }
  return words;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function draw(placeholder) {
  const plantuml = await engine();
  const files = await model();
  const source = await new Promise((resolve, reject) => {
    plantuml.sysmlToPlantUml(
      files.names,
      files.texts,
      optionWords(placeholder.dataset.sysmlOptions),
      resolve,
      reject
    );
  });
  const lines = ["@startuml", ...source.split("\n"), "@enduml"];
  return new Promise((resolve, reject) => {
    plantuml.renderToString(lines, resolve, reject);
  });
}

function drawLater(placeholder) {
  placeholder.dataset.sysmlState = "queued";
  drawQueue = drawQueue.then(async () => {
    if (!placeholder.isConnected) {
      return;
    }
    try {
      placeholder.innerHTML = await draw(placeholder);
      placeholder.dataset.sysmlState = "drawn";
    } catch (error) {
      placeholder.dataset.sysmlState = "error";
      placeholder.innerHTML =
        '<div class="sysml-diagram-error">' +
        escapeHtml(error && error.message ? error.message : error) +
        "</div>";
    }
  });
}

const visibility = new IntersectionObserver(
  (entries) => {
    for (const entry_ of entries) {
      if (entry_.isIntersecting) {
        visibility.unobserve(entry_.target);
        drawLater(entry_.target);
      }
    }
  },
  { rootMargin: "400px" }
);

function watch(placeholder) {
  if (placeholder.dataset.sysmlState !== undefined) {
    return;
  }
  placeholder.dataset.sysmlState = "waiting";
  visibility.observe(placeholder);
}

function newPlaceholder(options, className) {
  const placeholder = document.createElement("div");
  placeholder.className = `sysml-diagram ${className}`;
  placeholder.dataset.sysmlOptions = options;
  return placeholder;
}

// The diagram or the "Traces" button of each item of a SysML document.
async function addItemDiagrams() {
  if (document.querySelector('[data-sysml-document="true"]') === null) {
    return;
  }
  const anchors = document.querySelectorAll("sdoc-anchor[data-uid]");
  if (anchors.length === 0) {
    return;
  }
  const files = await model();
  for (const anchor_ of anchors) {
    const node = anchor_.closest("sdoc-node");
    if (node === null || node.querySelector(":scope > .sysml-item") !== null) {
      continue;
    }
    const uid = anchor_.dataset.uid;
    if (uid.includes("::")) {
      // A member of an item (a state of a state machine...), named by its
      // qualified name: not an item of its own.
      continue;
    }
    const container = document.createElement("div");
    container.className = "sysml-item";
    if (files.diagrams.has(uid)) {
      container.appendChild(
        newPlaceholder(`diagram=${uid} ${NODE_LINKS}`, "sysml-item-diagram")
      );
    } else if (files.roots.has(uid)) {
      container.appendChild(
        newPlaceholder(`root=${uid}`, "sysml-item-diagram")
      );
    } else {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "sysml-traces-button";
      button.textContent = "Traces";
      button.title = "Show the trace diagram of " + uid;
      button.addEventListener("click", () => {
        const shown = container.querySelector(".sysml-item-traces");
        if (shown !== null) {
          shown.remove();
          button.setAttribute("aria-pressed", "false");
          return;
        }
        button.setAttribute("aria-pressed", "true");
        const placeholder = newPlaceholder(
          `view=requirements focus=${uid} depth=1 ${NODE_LINKS}`,
          "sysml-item-traces"
        );
        container.appendChild(placeholder);
        watch(placeholder);
      });
      container.appendChild(button);
    }
    node.appendChild(container);
  }
}

let scanScheduled = false;

function scan() {
  scanScheduled = false;
  addItemDiagrams()
    .catch((error) => console.error("SysML diagrams:", error))
    .finally(() => {
      for (const placeholder_ of document.querySelectorAll(".sysml-diagram")) {
        watch(placeholder_);
      }
    });
}

function scheduleScan() {
  if (!scanScheduled) {
    scanScheduled = true;
    requestAnimationFrame(scan);
  }
}

function addStyle() {
  const style = document.createElement("style");
  style.textContent = `
    .sysml-diagram { overflow-x: auto; margin: 0.5em 0; }
    .sysml-diagram[data-sysml-state="drawn"] { cursor: zoom-in; }
    .sysml-diagram svg { max-width: 100%; height: auto; }
    .sysml-diagram.sysml-full-size { cursor: zoom-out; }
    .sysml-diagram.sysml-full-size svg { max-width: none; }
    .sysml-diagram[data-sysml-state="waiting"],
    .sysml-diagram[data-sysml-state="queued"] { min-height: 2em; }
    .sysml-diagram-error { color: #b00020; font-size: 0.85em;
      white-space: pre-wrap; }
    .sysml-item { margin-top: 0.5em; }
    .sysml-traces-button { font-size: 0.8em; cursor: pointer; }
  `;
  document.head.appendChild(style);
}

function toggleFullSize(event) {
  if (event.target.closest("a") !== null) {
    return;
  }
  const placeholder = event.target.closest(
    '.sysml-diagram[data-sysml-state="drawn"]'
  );
  if (placeholder !== null) {
    placeholder.classList.toggle("sysml-full-size");
  }
}

addStyle();
document.addEventListener("click", toggleFullSize);
scan();
new MutationObserver(scheduleScan).observe(document.body, {
  childList: true,
  subtree: true,
});
// After a save, the files changed: read them again and redraw.
document.addEventListener("turbo:before-stream-render", () => {
  modelPromise = null;
  for (const placeholder_ of document.querySelectorAll(
    '.sysml-diagram[data-sysml-state="drawn"]'
  )) {
    delete placeholder_.dataset.sysmlState;
  }
  requestAnimationFrame(() => requestAnimationFrame(scheduleScan));
});
