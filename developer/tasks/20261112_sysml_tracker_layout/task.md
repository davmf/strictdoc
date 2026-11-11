# SysML tracker layout: one file per item

## WHAT

StrictDoc shall read and write SysML v2 models in the tracker layout, where
each item is a separate `.sysml` file.

The layout:

- Each file holds one top-level package, named by the ID of what it holds.
  The file name is the ID.
- A tracker is a package with `@StrictDocWorkspace::Tracker` metadata
  (`title`, `kind`, `prefix`). A folder is a package with
  `@StrictDocWorkspace::Folder` metadata (`title`). An item package holds one
  element and the traces it is the client of.
- A tracker or a folder includes a child with `public import '<ID>'::*;`. The
  import order is the order of the children.
- The model root and library packages are not documents.

Reading:

- The layout is opt-in: `SysMLFormat(tracker_layout=True)`.
- Each tracker file is one document. Its folders are sections and its items
  are nodes, in import order.
- Only tracker files are documents. Folder files, item files, the model root
  and libraries are not.
- A tracker of requirement items is an editable requirements document.
  Any other tracker is a design document, as for single files.
- Errors stop the export and name the file: an include that names no file,
  an include cycle, a child included twice, a file whose top-level package
  name differs from its file name.
- A file in a tracker directory that nothing includes gives a warning.

Writing:

- A change to a requirement rewrites its item file only. The tracker and
  folder files change only when their children, titles or doc comments
  change. Files whose content does not change are not written.
- A new requirement gets an item file and an import line in its parent. A
  requirement without a UID gets the tracker prefix and the next free number.
- A deleted requirement loses its import line, and its item file is deleted.
- A moved requirement changes the import lines of the old and new parents.
- A new section gets a folder file with the ID `<prefix>-F-<TITLE>`.
- An item file keeps its imports. A new item file imports its tracker and
  the trackers of its trace targets.
- `#derivation` dependencies get `private import RequirementDerivation::*;`.
- The design element editor edits the item file of the element.

The single-file layout stays as it is.

## WHY

A Codebeamer-like workspace keeps the model as trackers, folders and items.
With one file per item, Git history is item history: a diff, a review or a
merge conflict concerns one item. The convention and its Pilot checks are in
the Halcyon repository, `docs/design/tracker_layout.md`.

## HOW

The reader turns a tracker and the files it includes into one in-memory
SysML model: the tracker package, folders as nested packages, and the members
of each item package inside its folder. The existing requirements and design
builders then build the document unchanged. Each node records its item file,
the item file's text hash and the item's imports.

The writer works on whole trackers. It renders every file of the tracker from
the document and writes the files whose text changed. It deletes the item
files of the tracker that no longer belong to it.

A new `Format.is_document_file(path)` hook, default `True`, lets
`DocumentFinder` skip files that are not documents (approved by the user,
2026-11-12). The SysML helpers in `main_router.py` take the node's item file
instead of the document file (approved, 2026-11-12).

Out of scope: the web UI tree, diagrams (PlantUML replaces Mermaid in a
later phase), a general `split` command.
