// Exported by StrictDoc. Do not edit: export the document again.
#import "company-report.typ": company-report
#import "kroki.typ": kroki
#import "strictdoc.typ": *

#show: company-report.with(
  title: "Widget Software Requirements",
  author: "Jo Bloggs",
  author_role: "Principal Software Engineer",
  doc_no: "298_1013",
  version: "02-draft",
  project: "Untitled Project",
  filename: "input.sdoc",
  date: datetime(year: 2026, month: 10, day: 29),
  revision-history: sd-revision-history(
    ([01], [Oct\-22, 2026], [Initial draft for review.]),
    ([02\-draft], [Oct\-29, 2026], [Added the #emph[display] requirements (see #link(label("SECT-DISPLAY"))[Display]).]),
  ),
)
#show: kroki

#outline(depth: 2)
#pagebreak()

#heading(level: 1)[Introduction]#label("SECT-INTRO")

This document specifies the widget software. Characters that Typst reads as markup must print as is: \# \* \_ \` \$ \< \> \@ \[ \] \~ \/\/ \= \- \+ and 1. at the start.

#metadata("ANCHOR-SCOPE")#label("ANCHOR-SCOPE")

The terms are:

#list([#strong[Widget]: the device.], [#raw("wsw"): the software, see #link("https://example.com")[the site].])

#sd-admonition([Note])[A note about the scope.]

#heading(level: 1)[Display]#label("SECT-DISPLAY")

#sd-requirements(
  (uid: "WSW-DSP-001", title: [Brightness], statement: [The software shall set the display brightness to between 10 % and 100 %.

#figure(table(
  columns: (50fr, 50fr,),
  table.header([Level], [Brightness]),
  [Low],
  [10 %],
  [High],
  [100 %],
), caption: [Brightness levels])], short-fields: (([Status], [Approved]), ([Verification], [T]),), fields: (([Rationale], [Readable in daylight, see #link(label("ANCHOR-SCOPE"))[Scope].]),), children: ([#link(label("WSW-DSP-002"))[WSW\-DSP\-002]],)),
  (uid: "WSW-DSP-002", statement: [The software shall show the logo below at start\-up:

#image("_assets/logo.svg", width: 75pt)], short-fields: (([Verification], [I]),), parents: ([#link(label("WSW-DSP-001"))[WSW\-DSP\-001]],)),
)

The start\-up sequence:

```mermaid
%%{init: {"htmlLabels": false, "fontFamily": "DejaVu Sans Mono", "flowchart": {"htmlLabels": false}}}%%
%% mermaid-name: input-diagram-1
graph TD
A[Power on] --> B(Logo)
```

#raw(block: true, lang: "c", "int brightness = 10;")
