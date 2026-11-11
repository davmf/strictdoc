# SysML diagrams with PlantUML

## WHAT

StrictDoc shall draw the diagrams of SysML documents with PlantUML, in the
browser, instead of Mermaid.

- Each SysML document starts with a diagram. A requirements document shows
  its requirements and what lies one relation away from them. A design
  document shows its definitions. In the tracker layout, the diagram covers
  the items that the tracker includes.
- In the tracker layout, an item that a SysML profile draws (a state
  machine, a sequence...) shows its diagram. A `view` item shows the saved
  diagram that it describes. The other items have a `Traces` button that
  shows their trace diagram.
- A box of a diagram links to its node.
- The server gives the browser the text of every `.sysml` file of the
  project at `GET /actions/sysml/model_files`, libraries included.
- StrictDoc reads `library package` files and `view` elements.

## WHY

The SysML profiles (state machines, sequences, timing diagrams...) and the
requirement views of PlantUML's `!include_sysml` draw what Mermaid cannot,
and the same engine draws the SysML playground of the PlantUML fork.

## HOW

The reader puts a placeholder at the top of each SysML document: a `div`
with the `!include_sysml` options and a module `script`
(`strictdoc/backend/sysml/diagram.py`). The script
(`strictdoc/features/plantuml/assets/plantuml/sysml/sysml-diagrams.js`)
loads the PlantUML engine (TeaVM, MIT license variant), elkjs and Viz.js,
fetches the model files and draws each placeholder when it scrolls into
view. It finds the items of the page through `sdoc-anchor[data-uid]`, and
asks the engine (`sysmlDescribe`) which UIDs are profile roots and saved
views. Links use `/?a=<UID>`, which the server resolves to the node.

The route is in a new feature router, `strictdoc/features/sysml_diagrams`,
registered in `strictdoc/server/app.py` (approved by the user, 2026-11-12).
The assets live in the folder of the PlantUML feature, which the server
already serves.

The diagrams need the server: the placeholder loads its script from an
absolute path and the model files come from the server.
