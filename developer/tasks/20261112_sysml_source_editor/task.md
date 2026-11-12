# SysML source editor on the workspace screen

## WHAT

The workspace screen shall edit the SysML source of an entry's file (item,
folder, tracker, model root):

- in a SysML editor with highlighting and folding;
- with a check of the text as it is typed (it parses, one top-level package
  named by the ID of the file), each problem with its line;
- with a preview of the entry's diagram drawn from the unsaved text;
- with a save that is refused, keeping the text, when the text has a
  problem, when the file changed on disk since the editor opened it, or
  when the tracker no longer reads with the text.

## WHY

The document screen edits fields, not the SysML of state machines,
sequences and timing diagrams, whose content is their structure.

## HOW

`/workspace?item=<ID>&edit=source` renders the editor form. workspace.js
replaces its textarea with the SysML editor of the PlantUML playground
(`sysml-editor.js` and its CodeMirror 6 bundle, copied from the PlantUML
fork). `sysml-editor.js` gets an `indent` option there, so that StrictDoc
indents with four spaces. `/workspace/check_source` checks the text without
saving. `/actions/sysml/workspace/save_source` (editor role) saves through
`sources.save_source()`: a hash of the file as opened detects changes on
disk, and the tracker is read again after the write, which is undone when
the read fails.
