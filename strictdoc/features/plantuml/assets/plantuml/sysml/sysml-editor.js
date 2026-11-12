// The playground's editors: CodeMirror 6 (vendor/codemirror-6.min.js) with
// small SysML v2 / KerML and PlantUML highlighters, behind the few calls
// sysml.js needs.
//
// SysML pane: each file keeps its own EditorState, so undo history, selections
// and scroll survive switching tabs, and an undo never reaches into another file.
// PlantUML pane: one document, rewritten by the import; those rewrites only
// replace what changed, so the cursor and scroll stay put, and they are not
// undo steps.
//
// Multi-cursor and friends come from CodeMirror's basicSetup:
//   Alt+click                     add a cursor
//   Alt+drag                      rectangular (column) selection
//   Ctrl/Cmd+Alt+Up/Down          add a cursor on the line above/below
//   Ctrl/Cmd+D                    select the next occurrence
//   Ctrl/Cmd+Shift+L              select every occurrence
//   Escape                        back to a single cursor
//   Ctrl/Cmd+F, Ctrl/Cmd+H        search, replace
//   Alt+Up/Down, Shift+Alt+Up/Down  move, copy the line
//   Ctrl/Cmd+/                    toggle a // (SysML) or ' (PlantUML) comment
//   Tab, Shift+Tab                indent, dedent (Escape then Tab leaves the editor)
//   Ctrl+Shift+[ / ]              fold, unfold the block at the cursor (Cmd+Alt+[ / ] on macOS)
//   Ctrl+Alt+[ / ]                fold, unfold all blocks
//   Ctrl+Alt+1 ... 9             unfold all, then fold the blocks at that level (1 = outermost)
//   Gutter arrows                fold, unfold one block with the mouse
//   Fold/unfold buttons          addFoldButtons(): the same actions, on each pane's header
// Blocks: { } in both languages; PlantUML also alt/opt/loop/par/group/critical/
// break/partition/box/ref/legend/note up to their end.
import {
	basicSetup, EditorView, EditorState, Transaction, keymap, placeholder, indentWithTab,
	StreamLanguage, syntaxHighlighting, indentUnit, classHighlighter, foldService,
	foldEffect, unfoldEffect, foldedRanges
} from "./vendor/codemirror-6.min.js";

const KEYWORDS = new Set((
	"about abstract accept action actor after alias all allocate allocation analysis and as assert assign assoc "
	+ "assume at attribute bind binding by calc case chains class classifier comment composite concern conjugate "
	+ "conjugates conjugation connect connection connector const constant constraint crosses datatype decide def "
	+ "default defined dependency derived differences disjoining disjoint do doc else end entry enum event exhibit "
	+ "exit expose expr false feature featured featuring filter first flow for fork frame from function hastype if "
	+ "implies import in include individual inout interaction interface intersects inv inverse inverting istype "
	+ "item join language library locale loop merge message meta metaclass metadata multiplicity namespace new "
	+ "nonunique not null objective occurrence of or ordered out package parallel part perform port portion "
	+ "predicate private protected public redefines redefinition ref references render rendering rep require "
	+ "requirement return satisfy send snapshot specialization specializes stakeholder standard state step struct "
	+ "subclassifier subject subset subsets subtype succession terminate then this timeslice to transition true "
	+ "type typed typing unions until use var variant variation verification verify via view viewpoint when while "
	+ "xor"
).split(" "));

const ATOMS = new Set(["true", "false", "null"]);

// Typing one of these inserts its closing pair. Not ': it opens a PlantUML
// comment, and in SysML it is mostly an apostrophe in a doc comment.
const CLOSE_BRACKETS = {brackets: ["(", "[", "{", "\""]};

// Brace depth drives the indentation of a new line; a name following "def"
// is a definition, a name following ":" or ":>" a type.
const sysmlLanguage = StreamLanguage.define({
	name: "sysml",
	startState: () => ({depth: 0, inComment: false, expect: null}),
	copyState: s => ({depth: s.depth, inComment: s.inComment, expect: s.expect}),
	token(stream, state) {
		if (state.inComment) {
			return blockComment(stream, state);
		}
		if (stream.eatSpace()) {
			return null;
		}
		if (stream.match("//")) {
			stream.skipToEnd();
			return "comment";
		}
		if (stream.match("/*")) {
			state.inComment = true;
			return blockComment(stream, state);
		}
		if (stream.match(/^"(?:[^"\\]|\\.)*"?/)) {
			return "string";
		}
		// Unrestricted name: 'any text'
		if (stream.match(/^'(?:[^'\\]|\\.)*'?/)) {
			return takeName(state);
		}
		if (stream.match(/^(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/)) {
			return "number";
		}
		if (stream.match(/^[#@][A-Za-z_][\w:]*/)) {
			return "meta";
		}
		if (stream.match(/^[A-Za-z_]\w*/)) {
			const word = stream.current();
			if (ATOMS.has(word)) {
				return "atom";
			}
			if (KEYWORDS.has(word)) {
				state.expect = word === "def" ? "def" : null;
				return "keyword";
			}
			return takeName(state);
		}
		if (stream.match(/^(?::>>|:>|::>|:=|::|=>|->|~)/)) {
			state.expect = stream.current() === "::" ? state.expect : "type";
			return "operator";
		}
		const ch = stream.next();
		if (ch === "{") {
			state.depth++;
			state.expect = null;
			return "brace";
		}
		if (ch === "}") {
			state.depth = Math.max(0, state.depth - 1);
			return "brace";
		}
		if (ch === ":") {
			state.expect = "type";
			return "operator";
		}
		if (ch === ";" || ch === ",") {
			state.expect = null;
			return "punctuation";
		}
		return /[=<>!+\-*\/%^&|]/.test(ch) ? "operator" : null;
	},
	indent(state, textAfter, cx) {
		if (state.inComment) {
			return null;
		}
		const depth = Math.max(0, state.depth - (/^\s*\}/.test(textAfter) ? 1 : 0));
		return depth * cx.unit;
	},
	languageData: {
		commentTokens: {line: "//", block: {open: "/*", close: "*/"}},
		indentOnInput: /^\s*\}$/,
		closeBrackets: CLOSE_BRACKETS
	}
});

// The rest of a /* */ comment on this line
function blockComment(stream, state) {
	if (stream.skipTo("*/")) {
		stream.match("*/");
		state.inComment = false;
	} else {
		stream.skipToEnd();
	}
	return "comment";
}

// A qualified name (A::B::C) keeps its role across the "::"
function takeName(state) {
	if (state.expect === "def") {
		state.expect = null;
		return "def";
	}
	if (state.expect === "type") {
		return "type";
	}
	return "variable";
}

// ---------------------------------------------------------------------------
// PlantUML
// ---------------------------------------------------------------------------

const PUML_KEYWORDS = new Set((
	"abstract activate actor again agent alt annotation archimate artifact as autonumber boundary box break "
	+ "card caption circle class cloud collections component control critical database deactivate destroy "
	+ "detach diamond direction else elseif end endbox endfork endif endlegend endnote endsplit endwhile entity "
	+ "enum exception file folder footer fork frame group harness header hexagon hide if interface json kill "
	+ "label left legend loop map metaclass namespace newpage node note object of on opt over package par "
	+ "participant partition port portin portout process protocol queue rectangle ref remove repeat return "
	+ "right show skinparam split stack start state stereotype stop storage struct style then title to together "
	+ "top bottom up down usecase while"
).split(" "));

// ' starts a comment only at the start of a line (elsewhere it is text, like
// an apostrophe in a message); /' '/ is a block comment.
const plantUmlLanguage = StreamLanguage.define({
	name: "plantuml",
	startState: () => ({inComment: false}),
	copyState: s => ({inComment: s.inComment}),
	token(stream, state) {
		if (state.inComment) {
			if (stream.skipTo("'/")) {
				stream.match("'/");
				state.inComment = false;
			} else {
				stream.skipToEnd();
			}
			return "comment";
		}
		if (stream.eatSpace()) {
			return null;
		}
		if (stream.match("/'")) {
			state.inComment = true;
			return "comment";
		}
		if (stream.peek() === "'" && stream.string.slice(0, stream.pos).trim() === "") {
			stream.skipToEnd();
			return "comment";
		}
		if (stream.match(/^@(?:start|end)\w+/)) {
			return "keyword";
		}
		if (stream.match(/^![A-Za-z_]\w*/)) {
			return "meta";
		}
		if (stream.match(/^%[A-Za-z_]\w*/)) {
			return "macroName";
		}
		if (stream.match(/^\$[A-Za-z_]\w*/)) {
			return "variableName.special";
		}
		if (stream.match(/^"(?:[^"\\]|\\.)*"?/)) {
			return "string";
		}
		if (stream.match(/^<<[^>]*>>/)) {
			return "labelName";
		}
		if (stream.match(/^#(?:[0-9A-Fa-f]{3,8}\b|[A-Za-z]\w*)/)) {
			return "atom";
		}
		// Arrows, with an optional [style] or direction inside: -->, -[#red]->, .up.>, <|--
		if (stream.match(/^(?:<\|?|[*o+#x}]|\\\\|\/\/)?(?:[-.=~]+(?:\[[^\]]*\]|left|right|up|down|le?|ri?|do?)?)+[-.=~]*(?:\|?>|[*o+#x{]|\\\\|\/\/)?/)
				&& /[-.=~]{2}|[<>]/.test(stream.current())) {
			return "operator";
		}
		stream.backUp(stream.current().length);
		if (stream.match(/^\d+(?:\.\d+)?/)) {
			return "number";
		}
		if (stream.match(/^[A-Za-z_][\w.]*/)) {
			return PUML_KEYWORDS.has(stream.current().toLowerCase()) ? "keyword" : null;
		}
		stream.next();
		return null;
	},
	languageData: {
		commentTokens: {line: "'", block: {open: "/'", close: "'/"}},
		closeBrackets: CLOSE_BRACKETS
	}
});

// ---------------------------------------------------------------------------
// Folding
// ---------------------------------------------------------------------------

// A line's text without what cannot open or close a block: strings and comments
function sysmlCode(text) {
	return text.replace(/"(?:[^"\\]|\\.)*"?|'(?:[^'\\]|\\.)*'?|\/\*.*?\*\/|\/\/.*$/g, "");
}

function plantUmlCode(text) {
	return /^\s*'/.test(text) ? "" : text.replace(/"(?:[^"\\]|\\.)*"?/g, "");
}

// Depth a code line adds: +1 for "{", -1 for "}"
function braceChange(code) {
	return (code.match(/\{/g) || []).length - (code.match(/\}/g) || []).length;
}

// PlantUML blocks without braces: "alt" ... "end", "note left of A" ... "end note".
// A colon or "as" makes a one-line note or ref, which has no end.
const PUML_BLOCK = "(?:alt|opt|loop|par|group|critical|break|partition|box|legend|note|ref)";
const PUML_OPENS = new RegExp("^\\s*" + PUML_BLOCK + "\\b", "i");
const PUML_ENDS = new RegExp("^\\s*end\\s*(?:" + PUML_BLOCK + ")?\\s*$", "i");

function pumlBlockChange(code) {
	if (PUML_ENDS.test(code)) {
		return -1;
	}
	return PUML_OPENS.test(code) && code.indexOf(":") < 0 && !/\bas\b/i.test(code) ? 1 : 0;
}

// Folds from the end of a line that opens a block to the line before the one
// that closes it. change(text) is the depth a line adds: +1 opens, -1 closes.
function blockFolds(change) {
	return (state, lineStart) => {
		const line = state.doc.lineAt(lineStart);
		let depth = change(line.text);
		if (depth <= 0) {
			return null;
		}
		for (let n = line.number + 1; n <= state.doc.lines; n++) {
			const next = state.doc.line(n);
			depth += change(next.text);
			if (depth <= 0) {
				return n > line.number + 1 ? {from: line.to, to: next.from - 1} : null;
			}
		}
		return null;
	};
}

// Every block in the document with its nesting depth (0 = outermost), found the
// same way as blockFolds. A block whose closing line directly follows its opener
// has no body to fold, so it is left out.
function blockRanges(doc, change) {
	const ranges = [];
	const open = [];
	for (let n = 1; n <= doc.lines; n++) {
		const line = doc.line(n);
		const delta = change(line.text);
		for (let i = 0; i < delta; i++) {
			open.push(n);
		}
		for (let i = 0; i > delta && open.length > 0; i--) {
			const start = open.pop();
			if (n > start + 1) {
				ranges.push({from: doc.line(start).to, to: line.from - 1, depth: open.length});
			}
		}
	}
	return ranges;
}

// Effects that unfold every folded range of the view's state
function unfoldEffects(state) {
	const effects = [];
	foldedRanges(state).between(0, state.doc.length, (from, to) => {
		effects.push(unfoldEffect.of({from, to}));
	});
	return effects;
}

// Unfolds everything, then folds the blocks at depth level - 1 (1 = outermost)
function foldToLevel(view, change, level) {
	const effects = unfoldEffects(view.state);
	const seen = new Set();
	for (const block of blockRanges(view.state.doc, change)) {
		const key = block.from + ":" + block.to;
		if (block.depth === level - 1 && seen.has(key) === false) {
			seen.add(key);
			effects.push(foldEffect.of({from: block.from, to: block.to}));
		}
	}
	if (effects.length === 0) {
		return false;
	}
	view.dispatch({effects});
	return true;
}

function unfoldAll(view) {
	const effects = unfoldEffects(view.state);
	if (effects.length === 0) {
		return false;
	}
	view.dispatch({effects});
	return true;
}

// Ctrl/Cmd+Alt+1 ... 9: unfold everything, then fold the blocks at that level
function foldLevelKeys(change) {
	const keys = [];
	for (let level = 1; level <= 9; level++) {
		keys.push({
			key: "Mod-Alt-" + level,
			run: view => foldToLevel(view, change, level)
		});
	}
	return keymap.of(keys);
}

function foldingFor(change) {
	return [foldService.of(blockFolds(change)), foldLevelKeys(change)];
}

const SYSML_BLOCKS = text => braceChange(sysmlCode(text));
const PUML_BLOCKS = text => braceChange(plantUmlCode(text)) + pumlBlockChange(plantUmlCode(text));

const sysmlFolds = foldingFor(SYSML_BLOCKS);
const plantUmlFolds = foldingFor(PUML_BLOCKS);

/**
 * Appends fold buttons to container for the editor view of the given language
 * ("sysml" or "plantuml"): Fold all, the levels 1 to 3, and Unfold all. They do
 * what the keys do, and give the focus back to the editor.
 */
export function addFoldButtons(container, view, language) {
	const change = language === "plantuml" ? PUML_BLOCKS : SYSML_BLOCKS;
	const add = (label, title, run) => {
		const button = document.createElement("button");
		button.type = "button";
		button.textContent = label;
		button.title = title;
		button.setAttribute("aria-label", title);
		button.addEventListener("click", () => {
			run();
			view.focus();
		});
		container.append(button);
	};
	add("Fold all", "Fold the outermost blocks (Ctrl/Cmd+Alt+1)", () => foldToLevel(view, change, 1));
	for (let level = 2; level <= 3; level++) {
		add("" + level, "Fold to level " + level + " (Ctrl/Cmd+Alt+" + level + ")",
			() => foldToLevel(view, change, level));
	}
	add("Unfold all", "Unfold all blocks (Ctrl/Cmd+Alt+])", () => unfoldAll(view));
}

// ---------------------------------------------------------------------------
// Editors
// ---------------------------------------------------------------------------

// The pane's look: main.css variables, so the dark toggle needs no theme swap.
const paneTheme = EditorView.theme({
	"&": {
		flexGrow: "1",
		minHeight: "0",
		height: "100%",
		fontSize: "0.85rem",
		color: "var(--fg)",
		backgroundColor: "transparent"
	},
	"&.cm-focused": {outline: "none"},
	".cm-scroller": {
		fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
		lineHeight: "1.45"
	},
	".cm-content": {caretColor: "var(--fg)", padding: "0.75rem 0 1.25rem"},
	".cm-cursor, .cm-dropCursor": {borderLeftColor: "var(--fg)"},
	".cm-gutters": {
		backgroundColor: "transparent",
		color: "var(--muted)",
		border: "none"
	},
	".cm-activeLine": {backgroundColor: "color-mix(in srgb, var(--accent) 12%, transparent)"},
	".cm-activeLineGutter": {backgroundColor: "transparent", color: "var(--fg)"},
	"&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground": {
		backgroundColor: "color-mix(in srgb, var(--accent) 45%, transparent)"
	},
	".cm-selectionMatch": {backgroundColor: "color-mix(in srgb, var(--accent) 25%, transparent)"},
	".cm-panels": {backgroundColor: "var(--surface)", color: "var(--fg)"},
	".cm-tooltip": {backgroundColor: "var(--surface)", color: "var(--fg)"},
	".cm-foldGutter .cm-gutterElement": {cursor: "pointer"},
	".cm-foldPlaceholder": {
		backgroundColor: "color-mix(in srgb, var(--accent) 18%, transparent)",
		border: "none",
		borderRadius: "3px",
		color: "var(--muted)",
		padding: "0 0.35em"
	}
});

// What both panes share. onChange(text) follows the edits made in the editor;
// a dispatch made while quiet() returns true is not reported.
function extensionsFor(language, folding, textarea, onChange, quiet, indent = "  ") {
	return [
		basicSetup,
		keymap.of([indentWithTab]),
		indentUnit.of(indent),
		EditorState.tabSize.of(4),
		language,
		folding,
		syntaxHighlighting(classHighlighter),
		paneTheme,
		placeholder(textarea.placeholder || ""),
		EditorView.contentAttributes.of({autocapitalize: "none", autocorrect: "off", spellcheck: "false"}),
		EditorView.updateListener.of(update => {
			if (update.docChanged && quiet() === false) {
				onChange(update.state.doc.toString());
			}
		})
	];
}

// The change from old to text as one replacement of the middle that differs,
// or null when they are equal: the cursor and the scroll outside it stay.
function changedMiddle(old, text) {
	if (old === text) {
		return null;
	}
	let from = 0;
	const max = Math.min(old.length, text.length);
	while (from < max && old.charCodeAt(from) === text.charCodeAt(from)) {
		from++;
	}
	let end = 0;
	while (end < max - from
		&& old.charCodeAt(old.length - 1 - end) === text.charCodeAt(text.length - 1 - end)) {
		end++;
	}
	return {from, to: old.length - end, insert: text.slice(from, text.length - end)};
}

// The textarea's place, id and classes go to the editor's host.
function replaceTextarea(textarea) {
	const host = document.createElement("div");
	host.id = textarea.id;
	host.className = textarea.className + " cm-host";
	textarea.replaceWith(host);
	return host;
}

/**
 * Replaces the textarea with the SysML editor; onChange(text) follows every
 * edit made in the editor (never the ones made through setFile).
 *
 * Returns {setFile(file), replaceText(file, text), focus()}: setFile shows a
 * {name, text} file, with the state it had when last shown unless its text
 * has changed since. replaceText changes a file from outside (a file changed
 * on disk) as one edit that Ctrl+Z undoes, shown or not; it sets file.text.
 *
 * options.indent is the text of one indentation level (default two spaces;
 * StrictDoc's SysML files use four).
 */
export function createSysmlEditor(textarea, onChange, options = {}) {
	const states = new WeakMap();
	let shown = null;
	let replacing = false;

	const extensions = extensionsFor(sysmlLanguage, sysmlFolds, textarea, onChange, () => replacing,
		options.indent).concat([
		// Dropped files open as tabs (the pane's drop handler), not as inserted text
		EditorView.domEventHandlers({
			drop: e => e.dataTransfer != null && e.dataTransfer.files.length > 0
		})
	]);
	const view = new EditorView({parent: replaceTextarea(textarea), state: EditorState.create({doc: "", extensions})});

	return {
		setFile(file) {
			if (shown != null && shown !== file) {
				states.set(shown, view.state);
			}
			if (shown === file && view.state.doc.toString() === file.text) {
				return;
			}
			const saved = states.get(file);
			view.setState(saved != null && saved.doc.toString() === file.text
				? saved
				: EditorState.create({doc: file.text, extensions}));
			shown = file;
		},
		replaceText(file, text) {
			const current = shown === file ? view.state : states.get(file);
			file.text = text;
			if (current == null || current.doc.toString() === text) {
				return; // never shown: setFile starts it from file.text
			}
			const changes = changedMiddle(current.doc.toString(), text);
			if (shown === file) {
				replacing = true;
				try {
					view.dispatch({changes, userEvent: "input.replace"});
				} finally {
					replacing = false;
				}
			} else {
				states.set(file, current.update({changes, userEvent: "input.replace"}).state);
			}
		},
		focus() {
			view.focus();
		},
		view
	};
}

/**
 * Replaces the textarea with the PlantUML editor; onChange(text) follows every
 * edit made in the editor (never the ones made by setting value).
 *
 * Returns {value, focus()}, value read and written like a textarea's.
 */
export function createPlantUmlEditor(textarea, onChange) {
	let setting = false;
	const extensions = extensionsFor(plantUmlLanguage, plantUmlFolds, textarea, onChange, () => setting);
	const view = new EditorView({parent: replaceTextarea(textarea), state: EditorState.create({doc: "", extensions})});

	return {
		get value() {
			return view.state.doc.toString();
		},
		// Only the changed middle is replaced: a re-import that changes one line
		// leaves the cursor, the selection and the scroll where they were.
		set value(text) {
			const changes = changedMiddle(view.state.doc.toString(), text);
			if (changes == null) {
				return;
			}
			setting = true;
			try {
				view.dispatch({
					changes,
					annotations: Transaction.addToHistory.of(false)
				});
			} finally {
				setting = false;
			}
		},
		focus() {
			view.focus();
		},
		view
	};
}
