"""
The PlantUML diagram at the top of each SysML document.

StrictDoc does not draw the diagram itself. The document gets a placeholder
with the options of a PlantUML `!include_sysml` directive, and the browser
draws it with the PlantUML engine (TeaVM build, MIT license), from the
SysML files of the project:

- a requirements document: the requirements of its package or tracker and
  what lies one relation away from them, without their text (the nodes
  below show it), each box a link to its node
  (`view=requirements root=<package> depth=1 text=false links=/?a={id}`);
- a design document: the definitions of its package or tracker
  (`view=definitions root=<package>`).

The script that draws the placeholders is
`strictdoc/features/plantuml/assets/plantuml/sysml/sysml-diagrams.js`. It
also adds the diagrams of the items of the page: the diagram of a state
machine, a sequence or another profile root, the saved views, and a trace
diagram on demand for the other items.
"""

import html

# The URL of the nodes, for `links=`: StrictDoc resolves `/?a=<UID>` to
# the node with this UID.
NODE_LINK_PATTERN = "/?a={id}"
SCRIPT_PATH = "plantuml/sysml/sysml-diagrams.js"


def diagram_options(root_name: str, is_design: bool) -> str:
    """
    The !include_sysml options of the diagram of a document. A value with
    spaces is written `key="a b"`.
    """
    quoted_root = _quote_option(root_name)
    if is_design:
        return f"view=definitions root={quoted_root}"
    return (
        f"view=requirements root={quoted_root} depth=1 text=false "
        f"links={NODE_LINK_PATTERN}"
    )


def as_rst_raw_html(options: str, static_directory: str) -> str:
    """
    The placeholder of a diagram and the script that draws it, as an RST raw
    HTML block. The browser runs the script once, however many placeholders
    a page has.
    """
    script_url = f"/{static_directory.strip('/')}/{SCRIPT_PATH}"
    return "\n".join(
        [
            ".. raw:: html",
            "",
            (
                '    <div class="sysml-diagram" data-sysml-document="true"'
                f' data-sysml-options="{html.escape(options)}"></div>'
            ),
            (
                '    <script type="module"'
                f' src="{html.escape(script_url)}"></script>'
            ),
        ]
    )


def _quote_option(value: str) -> str:
    if any(character_.isspace() for character_ in value):
        return '"' + value.replace('"', "'") + '"'
    return value
