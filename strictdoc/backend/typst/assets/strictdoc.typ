// Components of the Typst documents that StrictDoc exports.
//
// StrictDoc writes this file next to the exported documents. The documents
// call these functions rather than laying out their content themselves, so
// changing the look of requirements means changing this file only. The page
// layout (letterhead, header, footer, author table) comes from the report
// template that each document imports.

#let sd-requirement-uid(r) = {
  let uid = r.at("uid", default: none)
  if uid != none {
    // The label makes the requirement a target of links.
    [#metadata(uid)#label(uid)#text(size: 9pt, raw(uid))]
  } else {
    []
  }
}

#let sd-requirement-body(r) = {
  let parts = ()
  let title = r.at("title", default: none)
  if title != none {
    parts.push(strong(title))
  }
  let statement = r.at("statement", default: none)
  if statement != none {
    parts.push(statement)
  }
  let short-fields = r.at("short-fields", default: ())
  if short-fields.len() > 0 {
    parts.push(text(size: 8pt, short-fields.map(f => [#emph(f.at(0)): #f.at(1)]).join([ · ])))
  }
  for f in r.at("fields", default: ()) {
    parts.push([#strong[#f.at(0):] #f.at(1)])
  }
  let relations = ()
  let parents = r.at("parents", default: ())
  if parents.len() > 0 {
    relations.push([Parents: #parents.join([, ])])
  }
  let children = r.at("children", default: ())
  if children.len() > 0 {
    relations.push([Children: #children.join([, ])])
  }
  if relations.len() > 0 {
    parts.push(text(size: 8pt, relations.join([ · ])))
  }
  if parts.len() == 0 { [] } else { parts.join(parbreak()) }
}

// A table of requirements: the UID in the first column, and the title,
// statement, other fields and relations in the second. Each requirement is a
// dictionary with these keys, all optional:
//   uid:          string
//   title:        content
//   statement:    content
//   short-fields: array of (name, value) content pairs, written on one line
//   fields:       array of (name, value) content pairs, written as paragraphs
//   parents:      array of content
//   children:     array of content
#let sd-requirements(..requirements) = table(
  columns: (2.7cm, 1fr),
  align: left + top,
  table.header([ID], [Requirement]),
  ..requirements.pos().map(r => (sd-requirement-uid(r), sd-requirement-body(r))).flatten(),
)

// The revision history table of the cover page, one (revision, date,
// description) row per REVISION node of the document.
#let sd-revision-history(..rows) = {
  text(size: 1.4em, weight: "bold")[Revision History]
  v(-3mm)
  table(
    columns: (auto, auto, 1fr),
    table.header([*Revision*], [*Date*], [*Description*]),
    ..rows.pos().flatten(),
  )
}

// A link to a node of another document, which is not part of this PDF.
#let sd-external-link(title, document) = [#title (#emph(document))]

#let sd-admonition(title, body) = block(
  fill: rgb("#eef4fb"),
  stroke: (left: 2pt + rgb("#4a7ab8")),
  inset: (x: 8pt, y: 6pt),
  width: 100%,
  [#strong(title) \ #body],
)

// RST math is LaTeX, which Typst does not read. It is shown as source text.
#let sd-latex(source) = raw(source)
#let sd-latex-block(source) = raw(block: true, source)

#let sd-missing-image(path) = text(fill: rgb("#a00000"))[Missing image: #raw(path)]
