// A stand-in for the kroki.typ show rule of a build image, which
// draws diagrams from SVG files that a Kroki server renders. It draws a box
// in place of each diagram, so that the tests need no Kroki server.
#let kroki(cache-dir: ".kroki-cache", body) = {
  show raw.where(lang: "mermaid"): it => rect[Mermaid diagram]
  show raw.where(lang: "plantuml"): it => rect[PlantUML diagram]
  body
}
