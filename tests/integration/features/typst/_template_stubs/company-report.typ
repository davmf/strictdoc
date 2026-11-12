// A stand-in for the company-report template, which is not part of StrictDoc.
// It takes the same arguments, so that the tests can compile the exported
// documents.
#let company-report(
  title: "",
  author: "",
  author_role: "",
  author_company: "",
  doc_no: "",
  version: "",
  project: "",
  filename: "",
  repo: "",
  date: datetime.today(),
  dark-mode: false,
  revision-history: none,
  foreground: none,
  body,
) = {
  set document(title: title, author: author, date: date)
  set page(paper: "a4", header: [#doc_no #h(1fr) #title #h(1fr) #version])
  set heading(numbering: "1.1")
  [#author, #author_role]
  if revision-history != none {
    revision-history
  }
  pagebreak()
  body
}
