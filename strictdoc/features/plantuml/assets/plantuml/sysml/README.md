# SysML diagrams

The browser draws the diagrams of SysML documents with these files:

- `sysml-diagrams.js`: finds the diagram placeholders of a page, gets the
  SysML files of the project from `/sysml/model_files` and draws
  each placeholder. It also adds the diagrams of the items of the page.
  See `strictdoc/backend/sysml/diagram.py`.
- `plantuml-mit.js`: the PlantUML engine compiled to JavaScript by TeaVM,
  MIT license variant, with `!include_sysml` (`sysmlToPlantUml`,
  `sysmlDescribe`). Built from the PlantUML fork, branch
  `feature/strictdoc-workspace`, with
  `./gradlew -Pci :plantuml-mit:generateJavaScript`
  (`license-variants/plantuml-mit/build/generated/teavm/js/plantuml-mit.js`).
  License: `../LICENSE-PLANTUML`.
- `elk.bundled.js`: elkjs 0.12.1, the ELK layout used by most SysML
  diagrams. License: `elkjs-LICENSE.md` (EPL-2.0).

Graphviz (`../viz-global.js`, Viz.js 3.24.0) is shared with the PlantUML
code blocks of StrictDoc.
