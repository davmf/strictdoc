// Shows the diagrams that strictdoc-typst-build drew.
//
// A document exported with typst_kroki imports this file and applies it with
// "#show: kroki". strictdoc-typst-build draws each named PlantUML block to
// <cache-dir>/<name>.svg and lists the names in <cache-dir>/manifest.json.
// A block of a listed name shows its SVG file. Any other block is left to
// the report template, which shows it as source text.
//
// The name of a PlantUML block is the word after "@startuml", which
// StrictDoc writes. Keep the matching in step with strictdoc-typst-build.

#let kroki(cache-dir: ".kroki-cache", body) = {
  let rendered = json(cache-dir + "/manifest.json")

  show raw.where(block: true): it => {
    let names = rendered.at(str(it.lang), default: ())
    let match = if it.lang == "plantuml" {
      it.text.match(regex("@start\w*[ \t]+([\w-]+)"))
    }
    if match == none or match.captures.at(0) not in names {
      return it
    }
    let path = cache-dir + "/" + match.captures.at(0) + ".svg"
    // Shown at its own size, but no wider than the page.
    align(center, layout(size => {
      let diagram = image(path)
      if measure(diagram).width > size.width {
        image(path, width: 100%)
      } else {
        diagram
      }
    }))
  }

  body
}
