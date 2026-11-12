# SysML workspace screen

## WHAT

In the tracker layout, the StrictDoc server shall show a workspace screen at
`/workspace`, in the style of Codebeamer:

- On the left, one tree for the whole model: the model root, its trackers,
  their folders and their items. Each item has an icon for its kind
  (requirement, test case, part, state machine, sequence, timing
  diagram...). A filter box narrows the tree by ID or title.
- In the middle, the selected entry:
  - an item: its ID, title, kind, file and fields, then its diagram (the
    profile diagram of a state machine or another profile root, the saved
    diagram of a view, the trace diagram of the other items);
  - a tracker or a folder: its diagram and a table of what it holds;
  - the model root: a table of its trackers.
- On the right, the relations of the selected entry (to and from other
  items) and the Git history of its file.
- From the screen, a user creates a tracker, a folder or an item. An item is
  created from a template for its kind. The new file is included by its
  parent and the server reads the model again. Nothing is committed: the
  edits pile up for a later commit.
- Each entry links to its node on the document screen, where its fields are
  edited.

## WHY

A layered system model needs an overview of all its trackers at once, and a
quick way to add items of every kind, as in Codebeamer. The document screen
shows one tracker at a time.

## HOW

A new feature package, `strictdoc/features/sysml_workspace`:

- `workspace.py` reads the model from the SysML files: the model file
  (`@StrictDocWorkspace::Model`), the trackers with `tracker.read_tracker`
  and their nodes with `SysMLReader.read_from_tracker_file`. The model is
  kept until a `.sysml` file of the project changes.
- `history.py` reads the Git history of a file with `git log`.
- `templates.py` holds the templates of new items and writes the new files
  and the includes.
- `router.py` serves the screen and the create actions. Its own Jinja loader
  puts the feature's templates before StrictDoc's, so the screen extends the
  shared base layout without changing it.

The routes join the SysML diagrams router, which `app.py` already registers.
The create actions are under `/actions/`, so they need the editor role. They
rebuild the traceability index with `app.state.rebuild_and_notify_clients`,
like the project actions. The assets live next to the SysML diagram script,
in the folder of the PlantUML feature, which the server already serves.
