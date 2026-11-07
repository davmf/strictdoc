r"""
Builds the markup that renders SysML files with PlantUML in the browser.

With SysMLFormat(diagram_engine="plantuml"), a SysML document shows a
PlantUML diagram instead of the Mermaid diagram of diagram.py, and each
requirement shows a trace diagram below its statement. The page carries the
SysML text, and plantuml.js turns it into PlantUML with the sysmlToPlantUml
function of the vendored engine, then renders the result:

    <div class="sysml_sources" data-sysml-set="reqs.sysml" hidden>
      <script type="text/sysml" data-name="reqs.sysml">...</script>
      <script type="text/sysml" data-name="design.sysml">...</script>
    </div>
    <div class="sysml_diagram" data-sysml-set="reqs.sysml"
         data-sysml-options="view=definitions"></div>

The sources are written once per document, in place of the statement of its
diagram node. A diagram names the set of sources it uses, so the trace
diagrams of the requirements reuse the sources of their document. A set
holds:

- the file of the document, first,
- the files that it imports, followed through their own imports, found by
  the name of their top-level package,
- the files of the nodes that its nodes have a relation with, in both
  directions, without following them further.

This is enough to resolve a requirement of another file that a design
element satisfies, and to draw a trace of depth 1 in both directions. A
project-wide set would make every page carry every file.

The text of a <script> element ends at the first `</script`, and `<!--`
can hide that end. Each `<` that comes before `/` or `!` is written as
`\u003C`, and each backslash as `\u005C`, so the text has neither, and
plantuml.js decodes both.

The view names and options of the diagrams are defined here, in
DESIGN_DOCUMENT_OPTIONS, REQUIREMENTS_DOCUMENT_OPTIONS,
PROFILE_DOCUMENT_OPTIONS and requirement_view_options(). A document diagram
is limited to the top-level package of its file with root=, since its set
also holds the files of other documents.
"""

import html
import re
from typing import (
    TYPE_CHECKING,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from markupsafe import Markup

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sysml import node_data
from strictdoc.backend.sysml.model import (
    SysMLElement,
    SysMLImport,
    SysMLMember,
    SysMLModel,
    SysMLPackage,
)
from strictdoc.backend.sysml.version_tracking import (
    is_sysml_document,
    iterate_nodes,
)
from strictdoc.helpers.file_system import file_open_read_utf8

if TYPE_CHECKING:
    from strictdoc.core.traceability_index import TraceabilityIndex

MERMAID_ENGINE = "mermaid"
PLANTUML_ENGINE = "plantuml"
DIAGRAM_ENGINES = (MERMAID_ENGINE, PLANTUML_ENGINE)

# The diagram of a design document: a class diagram of its definitions.
DESIGN_DOCUMENT_OPTIONS: Tuple[str, ...] = ("view=definitions",)

# The diagram of a requirements document, which has no definitions: its
# requirements and the relations between them.
REQUIREMENTS_DOCUMENT_OPTIONS: Tuple[str, ...] = ("view=requirements",)

# The diagram of a document that imports a PlantUML SysML profile: no
# view, so the engine finds the root of the profile and draws it.
PROFILE_DOCUMENT_OPTIONS: Tuple[str, ...] = ()

# The packages of the profiles that the PlantUML SysML import draws, see
# docs/SYSML_PROFILES.md in the PlantUML repository.
PROFILE_PACKAGES = frozenset(
    {
        "ActivityProfile",
        "COTSDeviceProfile",
        "InterPCBAProfile",
        "InterconnectProfile",
        "PCBAProfile",
        "SequenceProfile",
        "SoftwareArchitectureProfile",
        "StateMachineProfile",
        "TimingProfile",
    }
)

# The node types that get a trace diagram.
TRACE_DIAGRAM_NODE_TYPES = frozenset({"REQUIREMENT"})


def requirement_view_options(uid: str) -> Tuple[str, ...]:
    """The options of the trace diagram of a requirement."""
    return ("view=requirements", f"focus={uid}", "depth=1")


def collect_packages(model: SysMLModel) -> Tuple[List[str], List[str]]:
    """
    Return the names of the top-level packages of a model and the targets
    of all its imports, in file order.
    """
    package_names = [
        member_.name
        for member_ in model.members
        if isinstance(member_, SysMLPackage) and member_.name is not None
    ]
    import_targets: List[str] = []

    def visit(members: Iterable[SysMLMember]) -> None:
        for member_ in members:
            if isinstance(member_, SysMLImport):
                import_targets.append(member_.target)
            elif isinstance(member_, (SysMLPackage, SysMLElement)):
                visit(member_.members)

    visit(model.members)
    return package_names, import_targets


def imported_package(import_target: str) -> str:
    """Return the first segment of an import target, unquoted."""
    return import_target.split("::", maxsplit=1)[0].strip().strip("'")


def document_options(document: SDocDocument) -> Tuple[str, ...]:
    for target_ in node_data.get_import_targets(document):
        if imported_package(target_) in PROFILE_PACKAGES:
            return PROFILE_DOCUMENT_OPTIONS
    options = (
        DESIGN_DOCUMENT_OPTIONS
        if node_data.is_design_document(document)
        else REQUIREMENTS_DOCUMENT_OPTIONS
    )
    package_names = node_data.get_package_names(document)
    if len(package_names) == 1:
        return (*options, f"root={package_names[0]}")
    return options


def has_trace_diagram(node: SDocNode) -> bool:
    return node.node_type in TRACE_DIAGRAM_NODE_TYPES and isinstance(
        node.reserved_uid, str
    )


def source_name(document: SDocDocument) -> str:
    """The name of the file of a document: its path in the project."""
    assert document.meta is not None
    return document.meta.input_doc_rel_path.relative_path_posix


def select_documents(
    document: SDocDocument, traceability_index: "TraceabilityIndex"
) -> List[SDocDocument]:
    """
    Return the SysML documents whose files a diagram of the document needs:
    the document first, then the others by file name.
    """
    sysml_documents = [
        document_
        for document_ in traceability_index.document_tree.document_list
        if is_sysml_document(document_)
    ]
    documents_by_package: Dict[str, SDocDocument] = {}
    for document_ in sysml_documents:
        for package_name_ in node_data.get_package_names(document_):
            documents_by_package.setdefault(package_name_, document_)

    selected: Set[int] = {id(document)}
    result: List[SDocDocument] = []

    def add(document_: Optional[SDocDocument]) -> bool:
        if (
            document_ is None
            or id(document_) in selected
            or not is_sysml_document(document_)
        ):
            return False
        selected.add(id(document_))
        result.append(document_)
        return True

    # Imports, followed through the imports of the imported files.
    pending = [document]
    while len(pending) > 0:
        importing = pending.pop()
        for target_ in node_data.get_import_targets(importing):
            imported = documents_by_package.get(imported_package(target_))
            if imported is not None and add(imported):
                pending.append(imported)

    # The documents of the nodes that a node of the document relates to.
    for node_ in iterate_nodes(document):
        related = [
            *traceability_index.get_parent_relations_with_roles(node_),
            *traceability_index.get_child_relations_with_roles(node_),
        ]
        for related_node_, _ in related:
            related_document = related_node_.get_document()
            if isinstance(related_document, SDocDocument):
                add(related_document)

    result.sort(key=source_name)
    return [document, *result]


def encode_script_text(text: str) -> str:
    """
    Make a text safe inside a <script> element, see the module docstring.
    """
    text = text.replace("\\", "\\u005C")
    return re.sub(r"<(?=[/!])", r"\\u003C", text)


def format_options(options: Sequence[str]) -> str:
    """
    Join the options into the value of data-sysml-options. An option whose
    value has spaces is written as key="value".
    """
    words: List[str] = []
    for option_ in options:
        key, separator, value = option_.partition("=")
        value = value.replace('"', "")
        if separator and re.search(r"\s", value) is not None:
            words.append(f'{key}="{value}"')
        else:
            words.append(f"{key}{separator}{value}")
    return " ".join(words)


def render_sources(set_id: str, sources: Sequence[Tuple[str, str]]) -> str:
    lines = [
        (
            '<div class="sysml_sources"'
            f' data-sysml-set="{_attribute(set_id)}" hidden>'
        )
    ]
    for name_, text_ in sources:
        lines.append(
            f'<script type="text/sysml" data-name="{_attribute(name_)}">'
            + encode_script_text(text_)
            + "</script>"
        )
    lines.append("</div>")
    return "\n".join(lines)


def render_block(
    set_id: str, options: Sequence[str], lazy: bool = False
) -> str:
    return (
        '<div class="sysml_diagram" data-testid="sysml-diagram"'
        f' data-sysml-set="{_attribute(set_id)}"'
        f' data-sysml-options="{_attribute(format_options(options))}"'
        + (' data-sysml-lazy="true"' if lazy else "")
        + "></div>"
    )


def render_document_diagram(
    document: SDocDocument, traceability_index: "TraceabilityIndex"
) -> Markup:
    """
    The sources of the document and its diagram, which replace the
    statement of its diagram node.
    """
    set_id = source_name(document)
    sources: List[Tuple[str, str]] = []
    for document_ in select_documents(document, traceability_index):
        assert document_.meta is not None
        with file_open_read_utf8(document_.meta.input_doc_full_path) as file_:
            sources.append((source_name(document_), file_.read()))
    return Markup(
        render_sources(set_id, sources)
        + "\n"
        + render_block(set_id, document_options(document))
    )


def render_trace_diagram(node: SDocNode) -> Markup:
    """The trace diagram of a node, which uses the sources of its document."""
    document = node.get_document()
    assert isinstance(document, SDocDocument)
    assert isinstance(node.reserved_uid, str)
    return Markup(
        render_block(
            source_name(document),
            requirement_view_options(node.reserved_uid),
            lazy=True,
        )
    )


def _attribute(value: str) -> str:
    return html.escape(value, quote=True)
