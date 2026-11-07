PlantUML engine for StrictDoc
=============================

plantuml-core.js is PlantUML compiled to JavaScript with TeaVM, converted
into a classic script that defines window.PlantUMLCore. viz-global.js is
Viz.js (Graphviz compiled to WebAssembly), which the engine uses for the
layout of most diagram types. elk.bundled.js is elkjs, the Eclipse Layout
Kernel, which the engine loads on demand for `!pragma layout elk`. The SysML
requirements view uses it by default.

Source:   https://github.com/davmf/plantuml
Branch:   feature/sysml-views
Commit:   197f3c39186db55f722d6817073968e101e060f5
Version:  1.2026.10beta1
Exports:  render, renderToString, sysmlToPlantUml, sysmlDescribe

To update, build the engine in the PlantUML checkout and vendor it:

    (cd <plantuml> && ./gradlew teavm -Pfast --offline)
    python developer/plantuml/vendor_plantuml_engine.py <plantuml>

Not vendored: the standard library bundles (`!include <C4/...>` and so on), emoji.js,
openiconic.js and themes.js. The engine loads them on demand, next to
plantuml-core.js, and reports an error when they are missing.

License: PlantUML is distributed under the GNU General Public License v3.0
or later (LICENSE-PLANTUML). Viz.js is MIT licensed and contains Graphviz
(Eclipse Public License 1.0) and Expat (MIT), see the header of
viz-global.js. elkjs is distributed under the Eclipse Public License 2.0, see
the header of elk.bundled.js.
