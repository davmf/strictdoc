"""
Converts RST text of node fields to Typst markup.

The RST text is parsed with docutils, the same parser that the HTML export
uses, and the document tree is written out as Typst. Only the constructs
that requirement text uses are written as Typst equivalents. Any other
construct is written as its plain text, and a warning is recorded.
"""

import html
import io
import os
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from docutils import nodes
from docutils.core import publish_doctree
from docutils.parsers.rst import directives, roles
from docutils.parsers.rst.states import Inliner

from strictdoc.backend.rst.directives.raw_html_role import raw_html_role
from strictdoc.backend.rst.directives.wildcard_enhanced_image import (
    STRICTDOC_FLAT_ASSETS_SETTING,
    STRICTDOC_REFERENCE_PATH_SETTING,
    WildcardEnhancedImage,
)
from strictdoc.backend.typst.typst_markup import escape_markup, string_literal

LINK_ROLE = "strictdoc-typst-link"
ANCHOR_ROLE = "strictdoc-typst-anchor"

# Diagram languages that the HTML export draws from
# <pre class="..."> raw HTML blocks.
DIAGRAM_LANGUAGES = ("mermaid", "plantuml")

# Languages that kroki.typ draws as diagrams when they appear as the
# language of a raw block. A code sample in one of them is written without
# a language, so that it stays a code sample.
KROKI_LANGUAGES = frozenset(
    (
        "actdiag",
        "blockdiag",
        "bpmn",
        "bytefield",
        "c4plantuml",
        "d2",
        "dbml",
        "ditaa",
        "erd",
        "excalidraw",
        "graphviz",
        "mermaid",
        "nomnoml",
        "nwdiag",
        "packetdiag",
        "pikchr",
        "plantuml",
        "rackdiag",
        "seqdiag",
        "structurizr",
        "svgbob",
        "symbolator",
        "tikz",
        "umlet",
        "vega",
        "vegalite",
        "wavedrom",
        "wireviz",
    )
)

# DejaVu Sans Mono is built into Typst, so the labels are drawn in the font
# that Mermaid measured them with.
MERMAID_SVG_LABELS_DIRECTIVE = (
    '%%{init: {"htmlLabels": false, "fontFamily": "DejaVu Sans Mono", '
    '"flowchart": {"htmlLabels": false}}}%%'
)

_DIAGRAM_HTML_REGEX = re.compile(
    r'^\s*<pre class="(?P<language>[a-z]+)">\n?(?P<source>.*?)</pre>\s*$',
    re.DOTALL,
)
# A node with the shape syntax of Mermaid 11.3, for example
# n18@{ shape: diam, label: "bubble1" }.
_MERMAID_SHAPE_NODE_REGEX = re.compile(
    r"^(?P<indent>\s*)(?P<node_id>[\w-]+)@\{(?P<body>[^}]*)\}\s*$"
)
_MERMAID_SHAPE_LABEL_REGEX = re.compile(r'label:\s*"(?P<label>[^"]*)"')
_MERMAID_SHAPE_NAME_REGEX = re.compile(r"shape:\s*(?P<shape>[\w-]+)")
_MERMAID_DIAMOND_SHAPES = ("diam", "diamond", "decision", "question", "rhombus")
_MERMAID_BAR_SHAPES = ("fork", "join")

_COLLAPSIBLE_HTML_REGEX = re.compile(
    r"</?details[^>]*>|<summary[^>]*>.*?</summary>", re.DOTALL
)
_MATH_HTML_REGEX = re.compile(r"\\\((?P<latex>.*?)\\\)", re.DOTALL)
_LENGTH_REGEX = re.compile(r"^(?P<value>\d+(\.\d+)?)\s*(?P<unit>[a-z%]*)$")

_ENUMERATION_PATTERNS = {
    "arabic": "1",
    "loweralpha": "a",
    "upperalpha": "A",
    "lowerroman": "i",
    "upperroman": "I",
}

_ADMONITION_TITLES = {
    "attention": "Attention",
    "caution": "Caution",
    "danger": "Danger",
    "error": "Error",
    "hint": "Hint",
    "important": "Important",
    "note": "Note",
    "tip": "Tip",
    "warning": "Warning",
}


class strictdoc_link(nodes.Inline, nodes.TextElement):  # type: ignore[misc]  # noqa: N801
    """A [LINK: ...] of a field, carried through the docutils parse."""


class strictdoc_anchor(nodes.Inline, nodes.TextElement):  # type: ignore[misc]  # noqa: N801
    """An [ANCHOR: ...] of a field, carried through the docutils parse."""


def _uid_role(
    node_class: Any,
) -> Callable[..., Tuple[List[nodes.Node], List[nodes.system_message]]]:
    def role(
        _name: str,
        rawtext: str,
        text: str,
        _lineno: int,
        _inliner: Inliner,
        _options: Optional[Dict[str, Any]] = None,
        _content: Optional[List[str]] = None,
    ) -> Tuple[List[nodes.Node], List[nodes.system_message]]:
        return [node_class(rawtext, text, uid=text)], []

    return role


directives.register_directive("image", WildcardEnhancedImage)
roles.register_local_role("rawhtml", raw_html_role)
roles.register_local_role(LINK_ROLE, _uid_role(strictdoc_link))
roles.register_local_role(ANCHOR_ROLE, _uid_role(strictdoc_anchor))


class RstToTypstConverter:
    def __init__(
        self,
        *,
        path_to_output_dir: str,
        render_link: Callable[[str], str],
        render_anchor: Callable[[str], str],
        diagram_name_prefix: str,
    ) -> None:
        """
        path_to_output_dir: the directory of the .typ file, which images are
                            looked up against.
        render_link:        writes the Typst of a [LINK: <uid>].
        render_anchor:      writes the Typst of an [ANCHOR: <uid>].
        diagram_name_prefix: makes the Kroki cache names of this document's
                            diagrams unique in the output directory.
        """
        self.path_to_output_dir: str = path_to_output_dir
        self.render_link: Callable[[str], str] = render_link
        self.render_anchor: Callable[[str], str] = render_anchor
        self.diagram_name_prefix: str = diagram_name_prefix
        self.diagram_count: int = 0
        self.has_diagrams: bool = False
        self.warnings: List[str] = []
        self._unsupported: Set[str] = set()
        self._footnotes: Dict[str, nodes.footnote] = {}

    def convert(self, rst_text: str) -> str:
        """Convert RST text to Typst block content."""
        doctree = self._parse(rst_text)
        return self._blocks(doctree.children)

    def convert_inline(self, rst_text: str) -> str:
        """
        Convert RST text to Typst, without a paragraph break when the text
        is a single paragraph, so that it can sit in a line of text.
        """
        doctree = self._parse(rst_text)
        children = [
            child_
            for child_ in doctree.children
            if not isinstance(child_, nodes.system_message)
        ]
        if len(children) == 1 and isinstance(children[0], nodes.paragraph):
            return self._inlines(children[0].children)
        return self._blocks(children)

    def _parse(self, rst_text: str) -> nodes.document:
        warning_stream = io.StringIO()
        doctree = publish_doctree(
            rst_text,
            source_path=os.path.join(
                self.path_to_output_dir, "STRICTDOC-FRAGMENT.rst"
            ),
            settings_overrides={
                "report_level": 5,
                "halt_level": 5,
                "warning_stream": warning_stream,
                "doctitle_xform": False,
                "sectsubtitle_xform": False,
                "syntax_highlight": "none",
                STRICTDOC_REFERENCE_PATH_SETTING: self.path_to_output_dir,
                STRICTDOC_FLAT_ASSETS_SETTING: True,
            },
        )
        self._footnotes = {}
        for footnote_ in doctree.findall(nodes.footnote):
            for id_ in footnote_["ids"]:
                self._footnotes[id_] = footnote_
        return doctree

    def _warn_unsupported(self, node: nodes.Node) -> None:
        name = node.__class__.__name__
        if name not in self._unsupported:
            self._unsupported.add(name)
            self.warnings.append(
                f"RST construct '{name}' has no Typst equivalent yet; "
                "it is written as plain text."
            )

    #
    # Block content.
    #

    def _blocks(self, children: List[nodes.Node]) -> str:
        blocks = []
        for child_ in children:
            block = self._block(child_)
            if len(block) > 0:
                blocks.append(block)
        return "\n\n".join(blocks)

    def _block(self, node: nodes.Node) -> str:
        if isinstance(
            node,
            (
                nodes.comment,
                nodes.target,
                nodes.substitution_definition,
                nodes.system_message,
                nodes.footnote,
                nodes.citation,
                nodes.decoration,
                nodes.pending,
            ),
        ):
            return ""
        if isinstance(node, nodes.paragraph):
            return self._paragraph(node)
        if isinstance(node, nodes.bullet_list):
            items = ", ".join(self._list_item(item_) for item_ in node.children)
            return f"#list({items})"
        if isinstance(node, nodes.enumerated_list):
            return self._enumerated_list(node)
        if isinstance(node, nodes.definition_list):
            return self._definition_list(node)
        if isinstance(node, nodes.field_list):
            return self._field_list(node)
        if isinstance(node, (nodes.literal_block, nodes.doctest_block)):
            return self._literal_block(node)
        if isinstance(node, nodes.math_block):
            return f"#sd-latex-block({string_literal(node.astext())})"
        if isinstance(node, nodes.raw):
            return self._raw(node, inline=False)
        if isinstance(node, nodes.table):
            return self._table(node)
        if isinstance(node, nodes.image):
            return self._image(node)
        if isinstance(node, nodes.figure):
            return self._figure(node)
        if isinstance(node, nodes.Admonition):
            return self._admonition(node)
        if isinstance(node, nodes.block_quote):
            return self._block_quote(node)
        if isinstance(node, nodes.line_block):
            return self._line_block(node)
        if isinstance(node, nodes.transition):
            return "#line(length: 100%)"
        if isinstance(node, (nodes.section, nodes.topic, nodes.sidebar)):
            return self._titled_container(node)
        if isinstance(node, nodes.rubric):
            return f"#strong[{self._inlines(node.children)}]"
        if isinstance(
            node,
            (nodes.container, nodes.compound, nodes.legend, nodes.list_item),
        ):
            return self._blocks(node.children)
        if isinstance(node, (nodes.Inline, nodes.Text)):
            return self._inline(node)
        self._warn_unsupported(node)
        return escape_markup(node.astext())

    def _paragraph(self, node: nodes.paragraph) -> str:
        return self._inlines(node.children).strip()

    def _list_item(self, node: nodes.Node) -> str:
        return f"[{self._blocks(node.children)}]"

    def _enumerated_list(self, node: nodes.enumerated_list) -> str:
        pattern = _ENUMERATION_PATTERNS.get(node.get("enumtype", "arabic"), "1")
        numbering = node.get("prefix", "") + pattern + node.get("suffix", ".")
        arguments = [f"numbering: {string_literal(numbering)}"]
        start = node.get("start", 1)
        if start != 1:
            arguments.append(f"start: {start}")
        arguments.extend(self._list_item(item_) for item_ in node.children)
        return f"#enum({', '.join(arguments)})"

    def _definition_list(self, node: nodes.definition_list) -> str:
        items = []
        for item_ in node.children:
            term = ""
            definition = ""
            for child_ in item_.children:
                if isinstance(child_, nodes.term):
                    term = self._inlines(child_.children)
                elif isinstance(child_, nodes.definition):
                    definition = self._blocks(child_.children)
            items.append(f"terms.item([{term}], [{definition}])")
        return f"#terms({', '.join(items)})"

    def _field_list(self, node: nodes.field_list) -> str:
        items = []
        for field_ in node.children:
            name = self._inlines(field_[0].children)
            body = self._blocks(field_[1].children)
            items.append(f"terms.item([{name}], [{body}])")
        return f"#terms({', '.join(items)})"

    def _literal_block(self, node: nodes.Element) -> str:
        arguments = ["block: true"]
        classes = [
            class_ for class_ in node.get("classes", []) if class_ != "code"
        ]
        if len(classes) > 0 and classes[0] not in KROKI_LANGUAGES:
            arguments.append(f"lang: {string_literal(classes[0])}")
        arguments.append(string_literal(node.astext()))
        return f"#raw({', '.join(arguments)})"

    def _raw(self, node: nodes.raw, inline: bool) -> str:
        formats = node.get("format", "").split()
        if "typst" in formats:
            return str(node.astext())
        if "html" in formats:
            raw_html = node.astext()
            if not inline and (
                diagram_match := _DIAGRAM_HTML_REGEX.match(raw_html)
            ):
                if diagram_match.group("language") in DIAGRAM_LANGUAGES:
                    return self._diagram(
                        diagram_match.group("language"),
                        html.unescape(diagram_match.group("source")),
                    )
            # A collapsible section has no meaning on paper: its content is
            # written out in full.
            if len(_COLLAPSIBLE_HTML_REGEX.sub("", raw_html).strip()) == 0:
                return ""
            if math_match := _MATH_HTML_REGEX.search(raw_html):
                latex = math_match.group("latex").strip()
                if inline:
                    return f"#sd-latex({string_literal(latex)})"
                return f"#sd-latex-block({string_literal(latex)})"
        self.warnings.append(
            f"Raw {node.get('format', '')} content is not written to Typst."
        )
        return ""

    def _diagram(self, language: str, source: str) -> str:
        """
        Write a diagram as a fenced raw block. render_kroki.py of the company
        typst-doc-builder renders each fenced block of a Kroki language to an
        SVG, which kroki.typ shows in place of the block. The name comment
        gives the SVG a stable file name.
        """
        self.has_diagrams = True
        self.diagram_count += 1
        name = f"{self.diagram_name_prefix}-diagram-{self.diagram_count}"
        lines = [line_.rstrip() for line_ in source.strip("\n").splitlines()]
        if language == "mermaid":
            lines = _with_classic_mermaid_shapes(lines)
            lines.insert(0, f"%% mermaid-name: {name}")
            # Typst does not draw the HTML labels that Mermaid puts in its
            # SVG by default, so ask for SVG text labels instead. Mermaid
            # merges this directive with any that the source has.
            lines.insert(0, MERMAID_SVG_LABELS_DIRECTIVE)
        elif language == "plantuml":
            if len(lines) > 0 and lines[0].strip() == "@startuml":
                lines[0] = f"@startuml {name}"
        # A fence inside the source would end the block early.
        source_text = "\n".join(lines).replace("```", "` ` `")
        return f"```{language}\n{source_text}\n```"

    def _table(self, node: nodes.table) -> str:
        caption: Optional[str] = None
        tgroup: Optional[nodes.tgroup] = None
        for child_ in node.children:
            if isinstance(child_, nodes.title):
                caption = self._inlines(child_.children)
            elif isinstance(child_, nodes.tgroup):
                tgroup = child_
        if tgroup is None:
            return ""

        column_widths = [
            colspec_.get("colwidth", 1)
            for colspec_ in tgroup.children
            if isinstance(colspec_, nodes.colspec)
        ]
        columns = ", ".join(f"{width_}fr" for width_ in column_widths)
        arguments = [f"columns: ({columns},)"]
        for section_ in tgroup.children:
            if isinstance(section_, nodes.thead):
                header_cells = self._table_rows(section_)
                arguments.append(f"table.header({', '.join(header_cells)})")
            elif isinstance(section_, nodes.tbody):
                arguments.extend(self._table_rows(section_))
        table = "table(\n  " + ",\n  ".join(arguments) + ",\n)"
        if caption is not None:
            return f"#figure({table}, caption: [{caption}])"
        return "#" + table

    def _table_rows(self, section: nodes.Element) -> List[str]:
        cells = []
        for row_ in section.children:
            for entry_ in row_.children:
                content = f"[{self._blocks(entry_.children)}]"
                cell_arguments = []
                if entry_.get("morecols", 0) > 0:
                    cell_arguments.append(f"colspan: {entry_['morecols'] + 1}")
                if entry_.get("morerows", 0) > 0:
                    cell_arguments.append(f"rowspan: {entry_['morerows'] + 1}")
                if len(cell_arguments) > 0:
                    content = (
                        f"table.cell({', '.join(cell_arguments)}){content}"
                    )
                cells.append(content)
        return cells

    def _image(self, node: nodes.image) -> str:
        uri: str = node["uri"]
        if "://" in uri:
            self.warnings.append(
                f"Remote image is not embedded in Typst output: {uri}"
            )
            return f"#link({string_literal(uri)})"
        if not os.path.isfile(os.path.join(self.path_to_output_dir, uri)):
            self.warnings.append(f"Image not found: {uri}")
            return f"#sd-missing-image({string_literal(uri)})"
        arguments = [string_literal(uri)]
        for dimension_ in ("width", "height"):
            if dimension_ in node:
                length = self._length(node[dimension_])
                if length is not None:
                    arguments.append(f"{dimension_}: {length}")
        if "alt" in node:
            arguments.append(f"alt: {string_literal(node['alt'])}")
        return f"#image({', '.join(arguments)})"

    @staticmethod
    def _length(rst_length: str) -> Optional[str]:
        """Convert an RST length (400, 400px, 50%, 3cm) to a Typst length."""
        match = _LENGTH_REGEX.match(rst_length.strip())
        if match is None:
            return None
        value = float(match.group("value"))
        unit = match.group("unit")
        if unit in ("", "px"):
            # CSS pixels: 96 per inch, 72 points per inch.
            return f"{value * 0.75:g}pt"
        if unit in ("%", "pt", "mm", "cm", "in", "em"):
            return f"{value:g}{unit}"
        return None

    def _figure(self, node: nodes.figure) -> str:
        body = ""
        caption: Optional[str] = None
        legend = ""
        for child_ in node.children:
            if isinstance(child_, nodes.image):
                body = self._image(child_).removeprefix("#")
            elif isinstance(child_, nodes.caption):
                caption = self._inlines(child_.children)
            elif isinstance(child_, nodes.legend):
                legend = self._blocks(child_.children)
        if len(body) == 0:
            return legend
        if caption is None:
            figure = f"#figure({body})"
        else:
            figure = f"#figure({body}, caption: [{caption}])"
        if len(legend) > 0:
            return f"{figure}\n\n{legend}"
        return figure

    def _admonition(self, node: nodes.Element) -> str:
        children = list(node.children)
        if isinstance(node, nodes.admonition):
            title = ""
            if len(children) > 0 and isinstance(children[0], nodes.title):
                title = self._inlines(children.pop(0).children)
        else:
            title = escape_markup(
                _ADMONITION_TITLES.get(node.tagname, node.tagname.title())
            )
        return f"#sd-admonition([{title}])[{self._blocks(children)}]"

    def _block_quote(self, node: nodes.block_quote) -> str:
        attribution = ""
        children = []
        for child_ in node.children:
            if isinstance(child_, nodes.attribution):
                attribution = self._inlines(child_.children)
            else:
                children.append(child_)
        if len(attribution) > 0:
            return (
                f"#quote(block: true, attribution: [{attribution}])"
                f"[{self._blocks(children)}]"
            )
        return f"#quote(block: true)[{self._blocks(children)}]"

    def _line_block(self, node: nodes.line_block) -> str:
        lines = []
        for child_ in node.children:
            if isinstance(child_, nodes.line):
                lines.append(self._inlines(child_.children))
            else:
                lines.append(self._line_block(child_))
        return " \\\n".join(lines)

    def _titled_container(self, node: nodes.Element) -> str:
        blocks = []
        for child_ in node.children:
            if isinstance(child_, nodes.title):
                blocks.append(f"#strong[{self._inlines(child_.children)}]")
            else:
                block = self._block(child_)
                if len(block) > 0:
                    blocks.append(block)
        return "\n\n".join(blocks)

    #
    # Inline content.
    #

    def _inlines(self, children: List[nodes.Node]) -> str:
        return "".join(self._inline(child_) for child_ in children)

    def _inline(self, node: nodes.Node) -> str:
        if isinstance(node, nodes.Text):
            # astext() drops the null characters that docutils keeps in
            # place of RST backslash escapes.
            return escape_markup(node.astext().replace("\n", " "))
        if isinstance(node, strictdoc_link):
            return self.render_link(node["uid"])
        if isinstance(node, strictdoc_anchor):
            return self.render_anchor(node["uid"])
        if isinstance(node, nodes.strong):
            return f"#strong[{self._inlines(node.children)}]"
        if isinstance(node, (nodes.emphasis, nodes.title_reference)):
            return f"#emph[{self._inlines(node.children)}]"
        if isinstance(node, nodes.literal):
            return f"#raw({string_literal(node.astext())})"
        if isinstance(node, nodes.subscript):
            return f"#sub[{self._inlines(node.children)}]"
        if isinstance(node, nodes.superscript):
            return f"#super[{self._inlines(node.children)}]"
        if isinstance(node, nodes.reference):
            return self._reference(node)
        if isinstance(node, nodes.footnote_reference):
            return self._footnote_reference(node)
        if isinstance(node, nodes.math):
            return f"#sd-latex({string_literal(node.astext())})"
        if isinstance(node, nodes.raw):
            return self._raw(node, inline=True)
        if isinstance(node, nodes.image):
            return self._image(node)
        if isinstance(
            node,
            (nodes.target, nodes.system_message, nodes.substitution_reference),
        ):
            return ""
        if isinstance(
            node,
            (
                nodes.inline,
                nodes.abbreviation,
                nodes.acronym,
                nodes.problematic,
                nodes.generated,
            ),
        ):
            return self._inlines(node.children)
        if isinstance(node, nodes.Element) and not isinstance(
            node, nodes.Inline
        ):
            return self._block(node)
        self._warn_unsupported(node)
        return escape_markup(node.astext())

    def _reference(self, node: nodes.reference) -> str:
        text = self._inlines(node.children)
        if "refuri" in node:
            return f"#link({string_literal(node['refuri'])})[{text}]"
        # A reference to a target inside the field, for example `Title`_.
        # The target has no counterpart in the Typst output.
        return text

    def _footnote_reference(self, node: nodes.footnote_reference) -> str:
        footnote = self._footnotes.get(node.get("refid", ""))
        if footnote is None:
            return ""
        body = [
            child_
            for child_ in footnote.children
            if not isinstance(child_, nodes.label)
        ]
        return f"#footnote[{self._blocks(body)}]"


def _with_classic_mermaid_shapes(lines: List[str]) -> List[str]:
    """
    Rewrite nodes with the shape syntax of Mermaid 11.3 to the older node
    syntax. The company Kroki server (Mermaid 11.12.3) rejects any diagram with
    a shape node, which the SysML diagrams use for decisions and forks. A
    decision becomes a rhombus, and a fork or join a small filled box.
    """
    output: List[str] = []
    bar_node_ids: List[str] = []
    for line_ in lines:
        match = _MERMAID_SHAPE_NODE_REGEX.match(line_)
        if match is None:
            output.append(line_)
            continue
        node_id = match.group("node_id")
        body = match.group("body")
        shape_match = _MERMAID_SHAPE_NAME_REGEX.search(body)
        shape = shape_match.group("shape") if shape_match is not None else ""
        label_match = _MERMAID_SHAPE_LABEL_REGEX.search(body)
        label = label_match.group("label") if label_match is not None else None
        indent = match.group("indent")
        if shape in _MERMAID_DIAMOND_SHAPES:
            output.append(f'{indent}{node_id}{{"{label or node_id}"}}')
        elif shape in _MERMAID_BAR_SHAPES:
            output.append(f'{indent}{node_id}[" "]')
            bar_node_ids.append(node_id)
        else:
            output.append(f'{indent}{node_id}["{label or node_id}"]')
    for node_id_ in bar_node_ids:
        output.append(f"  style {node_id_} fill:#333,stroke:#333")
    return output
