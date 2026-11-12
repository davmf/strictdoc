# Saved views on the SysML workspace screen

## WHAT

The workspace screen shall save and edit views: SysML `view` items that
PlantUML draws with `diagram=<ID>`.

- `Save as view` saves the diagram of an item, a tracker or a folder as a
  new view item, in a tracker that is not a requirements tracker.
- The view editor of a view item edits its title, description, exposed
  elements, options and PlantUML lines. It suggests what a view can expose,
  including the states of state machines.
- The diagram previews the fields as they are typed, before they are saved,
  and shows the errors of the engine.
- The relations of an item list the views that show it (role `Shows`).

## WHY

One state machine needs several diagrams: one per composite state, one with
the primary transitions only, one with review notes. Writing view files by
hand needs the syntax of exposes and options.

## HOW

`strictdoc/features/sysml_workspace/views.py` reads a view file into the
fields of the editor and writes the fields back (`view_text()`). The preview
posts the fields to `/workspace/view_source`, which returns the view text
without saving it. `sysml-diagrams.js` exports `drawWithFile()`, which draws
a diagram with one file replaced by that text. `save_view` and `new_view`
are under `/actions/`, so they need the editor role.
