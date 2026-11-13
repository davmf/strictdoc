// The report template of StrictDoc's Typst export.
//
// StrictDoc writes this file next to the exported documents. Each document
// applies it with "#show: strictdoc-report.with(...)". The template draws a
// title page with the document details and the revision history, and a
// header and footer on the other pages. It uses only the fonts that come
// with Typst, so the documents compile with a plain "typst compile".
//
// External templates (the typst_template option) take the same arguments,
// so that a project can switch between them.

#let _sd-detail-rows(details) = (
  details
    .filter(d => d.at(1) != none and d.at(1) != "")
    .map(d => (strong(d.at(0)), d.at(1)))
    .flatten()
)

#let strictdoc-report(
  title: "",
  author: "",
  author_role: "",
  doc_no: "",
  version: "",
  project: "",
  filename: "",
  date: none,
  revision-history: none,
  body,
) = {
  set document(
    title: title,
    author: if author == "" { () } else { author },
    date: if date == none { auto } else { date },
  )
  set text(size: 10.5pt)
  set par(justify: true)
  set heading(numbering: "1.1")
  show heading.where(level: 1): set block(above: 1.6em, below: 0.9em)
  set table(stroke: 0.5pt + luma(160), inset: 5pt)
  show table.cell.where(y: 0): set text(weight: "bold")

  // Diagrams are not rendered: their source is shown in a frame.
  show raw.where(block: true, lang: "mermaid"): it => block(
    width: 100%,
    stroke: 0.5pt + luma(160),
    inset: 8pt,
    [#text(size: 8pt, fill: luma(90))[Mermaid diagram source] \ #it],
  )
  show raw.where(block: true, lang: "plantuml"): it => block(
    width: 100%,
    stroke: 0.5pt + luma(160),
    inset: 8pt,
    [#text(size: 8pt, fill: luma(90))[PlantUML diagram source] \ #it],
  )

  let date-text = if date == none { "" } else {
    date.display("[day] [month repr:short] [year]")
  }
  let reference = (doc_no, version).filter(part => part != "").join(" ")

  set page(
    paper: "a4",
    margin: (x: 22mm, top: 25mm, bottom: 22mm),
    header: context {
      if counter(page).get().first() > 1 {
        set text(size: 8.5pt, fill: luma(80))
        grid(
          columns: (1fr, auto),
          title, if reference == none { [] } else { reference },
        )
        v(-0.6em)
        line(length: 100%, stroke: 0.4pt + luma(160))
      }
    },
    footer: context {
      set text(size: 8.5pt, fill: luma(80))
      grid(
        columns: (1fr, auto),
        project,
        counter(page).display("1 / 1", both: true),
      )
    },
  )

  // The title page.
  v(30mm)
  text(size: 24pt, weight: "bold", title)
  v(10mm)
  table(
    columns: (4.2cm, 1fr),
    stroke: none,
    inset: (x: 0pt, y: 4pt),
    .._sd-detail-rows((
      ("Document number", doc_no),
      ("Version", version),
      ("Date", date-text),
      ("Author", author),
      ("Author role", author_role),
      ("Project", project),
      ("Source file", filename),
    )),
  )
  if revision-history != none {
    v(12mm)
    revision-history
  }
  pagebreak()

  body
}
