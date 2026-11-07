import re
from typing import Dict, List, Tuple

import pytest

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sysml import node_data, plantuml_diagram
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.backend.sysml.sysml_format import (
    SysMLFormat,
    uses_plantuml_diagrams,
)
from strictdoc.backend.sysml.version_tracking import iterate_nodes
from strictdoc.core.document_meta import DocumentMeta
from strictdoc.core.document_tree import DocumentTree
from strictdoc.core.project_config import ProjectConfig
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.core.traceability_index_builder import TraceabilityIndexBuilder
from strictdoc.helpers.paths import SDocRelativePath

REQUIREMENTS_TEXT = """\
package Requirements {
    doc /*
     * A doc with a script end tag </script> and a comment <!-- x -->.
     */

    requirement <'REQ-1'> 'Open' {
        doc /*
         * The door shall open.
         */
    }

    requirement <'REQ-2'> 'Close' {
    }
}
"""

DESIGN_TEXT = """\
package Design {
    private import Parts::*;

    part def Door {
        part motor : Motor;
        satisfy 'REQ-1' by motor;
    }
}
"""

PARTS_TEXT = """\
package Parts {
    private import Units::*;

    part def Motor;
}
"""

UNITS_TEXT = """\
package Units {
    attribute def Volt;
}
"""

UNRELATED_TEXT = """\
package Unrelated {
    part def Lamp;
}
"""

STATE_MACHINE_TEXT = """\
package DoorController {
    private import StateMachineProfile::*;

    part doorSm : StateMachine {
        part :>> top : Region {
            part closed : State { :>> name = "Closed"; }
        }
    }
}
"""


def _read_documents(
    tmp_path, files: Dict[str, str]
) -> Tuple[Dict[str, SDocDocument], TraceabilityIndex, ProjectConfig]:
    project_config = ProjectConfig.default_config()
    project_config.formats = [
        *ProjectConfig.default_formats(),
        SysMLFormat(diagram_engine=plantuml_diagram.PLANTUML_ENGINE),
    ]
    documents: Dict[str, SDocDocument] = {}
    for name_, text_ in files.items():
        path_to_file = tmp_path / name_
        path_to_file.write_text(text_, encoding="utf-8")
        document = SysMLReader.read_from_string(
            text_, file_path=str(path_to_file), relative_path=name_
        )
        document.meta = DocumentMeta(
            level=0,
            file_tree_mount_folder="NOT_RELEVANT",
            document_filename=name_,
            document_filename_base=name_.replace(".sysml", ""),
            input_doc_full_path=str(path_to_file),
            input_doc_rel_path=SDocRelativePath(name_),
            input_doc_dir_rel_path=SDocRelativePath(""),
            input_doc_assets_dir_rel_path=SDocRelativePath("_assets"),
            output_document_dir_full_path="NOT_RELEVANT",
            output_document_dir_rel_path=SDocRelativePath("FIXME"),
        )
        documents[name_] = document
    document_tree = DocumentTree(
        file_tree=[],
        document_list=list(documents.values()),
        map_docs_by_paths={},
        map_docs_by_rel_paths={},
        map_grammars_by_filenames={},
    )
    traceability_index = TraceabilityIndexBuilder.create_from_document_tree(
        document_tree, project_config=project_config
    )
    return documents, traceability_index, project_config


def _names(documents: List[SDocDocument]) -> List[str]:
    return [plantuml_diagram.source_name(document_) for document_ in documents]


def _decode(text: str) -> str:
    """The decoding of plantuml.js."""
    return re.sub(
        r"\\u00(3C|5C)",
        lambda match_: "<" if match_.group(1) == "3C" else "\\",
        text,
    )


def _node(document: SDocDocument, uid: str) -> SDocNode:
    for node_ in iterate_nodes(document):
        if node_.reserved_uid == uid:
            return node_
    raise AssertionError(uid)


def test_collect_packages_lists_packages_and_nested_imports(tmp_path):
    documents, _, _ = _read_documents(
        tmp_path,
        {
            "requirements.sysml": REQUIREMENTS_TEXT,
            "design.sysml": DESIGN_TEXT,
            "parts.sysml": PARTS_TEXT,
        },
    )

    document = documents["design.sysml"]

    assert node_data.get_package_names(document) == ["Design"]
    assert node_data.get_import_targets(document) == ["Parts::*"]


def test_select_documents_follows_imports_and_relations(tmp_path):
    documents, traceability_index, _ = _read_documents(
        tmp_path,
        {
            "requirements.sysml": REQUIREMENTS_TEXT,
            "design.sysml": DESIGN_TEXT,
            "parts.sysml": PARTS_TEXT,
            "units.sysml": UNITS_TEXT,
            "unrelated.sysml": UNRELATED_TEXT,
        },
    )

    # The design imports Parts, which imports Units, and it satisfies a
    # requirement of requirements.sysml. The document comes first.
    assert _names(
        plantuml_diagram.select_documents(
            documents["design.sysml"], traceability_index
        )
    ) == [
        "design.sysml",
        "parts.sysml",
        "requirements.sysml",
        "units.sysml",
    ]
    # A requirement is satisfied by the design, whose imports are not
    # followed, since only the files of related nodes are added.
    assert _names(
        plantuml_diagram.select_documents(
            documents["requirements.sysml"], traceability_index
        )
    ) == ["requirements.sysml", "design.sysml"]
    assert _names(
        plantuml_diagram.select_documents(
            documents["unrelated.sysml"], traceability_index
        )
    ) == ["unrelated.sysml"]


@pytest.mark.parametrize(
    "text",
    [
        "a </script> b",
        "<!-- <script> -->",
        "back\\slash \\u003C \\u005C",
        "<'REQ-1'> stays readable",
        "",
    ],
)
def test_encode_script_text_round_trips(text):
    encoded = plantuml_diagram.encode_script_text(text)

    assert "</" not in encoded
    assert "<!" not in encoded
    assert _decode(encoded) == text


def test_encode_script_text_keeps_short_names_readable():
    assert (
        plantuml_diagram.encode_script_text("requirement <'REQ-1'> 'Open'")
        == "requirement <'REQ-1'> 'Open'"
    )


def test_format_options_quotes_values_with_spaces():
    assert (
        plantuml_diagram.format_options(
            ["view=requirements", "focus=REQ 1", "depth=1", 'root="x"']
        )
        == 'view=requirements focus="REQ 1" depth=1 root=x'
    )


def test_render_document_diagram_embeds_the_set_once(tmp_path):
    documents, traceability_index, _ = _read_documents(
        tmp_path,
        {"requirements.sysml": REQUIREMENTS_TEXT, "design.sysml": DESIGN_TEXT},
    )

    output = str(
        plantuml_diagram.render_document_diagram(
            documents["requirements.sysml"], traceability_index
        )
    )

    assert output.startswith(
        '<div class="sysml_sources" data-sysml-set="requirements.sysml" hidden>'
    )
    scripts = re.findall(
        r'<script type="text/sysml" data-name="([^"]+)">(.*?)</script>',
        output,
        re.DOTALL,
    )
    assert [name_ for name_, _ in scripts] == [
        "requirements.sysml",
        "design.sysml",
    ]
    assert _decode(scripts[0][1]) == REQUIREMENTS_TEXT
    assert _decode(scripts[1][1]) == DESIGN_TEXT
    # The only </script> tags are the ones that close the elements.
    assert output.count("</script") == 2
    assert output.endswith(
        '<div class="sysml_diagram" data-testid="sysml-diagram"'
        ' data-sysml-set="requirements.sysml"'
        ' data-sysml-options="view=requirements root=Requirements"></div>'
    )


def test_document_options_follow_the_kind_of_document(tmp_path):
    documents, _, _ = _read_documents(
        tmp_path,
        {
            "requirements.sysml": REQUIREMENTS_TEXT,
            "design.sysml": DESIGN_TEXT,
            "parts.sysml": PARTS_TEXT,
            "door.sysml": STATE_MACHINE_TEXT,
        },
    )

    # A requirements package has no definitions: it shows its requirements.
    assert plantuml_diagram.document_options(
        documents["requirements.sysml"]
    ) == ("view=requirements", "root=Requirements")
    # A design package shows the definitions of its own package only, not
    # those of the other files of its set.
    assert plantuml_diagram.document_options(documents["design.sysml"]) == (
        "view=definitions",
        "root=Design",
    )
    # A file typed with a profile is drawn by the profile.
    assert plantuml_diagram.document_options(documents["door.sysml"]) == ()


def test_render_document_diagram_lets_a_profile_pick_its_root(tmp_path):
    documents, traceability_index, _ = _read_documents(
        tmp_path, {"door.sysml": STATE_MACHINE_TEXT}
    )

    output = str(
        plantuml_diagram.render_document_diagram(
            documents["door.sysml"], traceability_index
        )
    )

    assert 'data-sysml-options=""' in output


def test_render_trace_diagram_uses_the_sources_of_the_document(tmp_path):
    documents, _, _ = _read_documents(
        tmp_path, {"requirements.sysml": REQUIREMENTS_TEXT}
    )
    requirement = _node(documents["requirements.sysml"], "REQ-1")

    assert plantuml_diagram.has_trace_diagram(requirement)
    assert str(plantuml_diagram.render_trace_diagram(requirement)) == (
        '<div class="sysml_diagram" data-testid="sysml-diagram"'
        ' data-sysml-set="requirements.sysml"'
        ' data-sysml-options="view=requirements focus=REQ-1 depth=1"'
        ' data-sysml-lazy="true"></div>'
    )


def test_design_nodes_have_no_trace_diagram(tmp_path):
    documents, _, _ = _read_documents(
        tmp_path,
        {"requirements.sysml": REQUIREMENTS_TEXT, "design.sysml": DESIGN_TEXT},
    )

    for node_ in iterate_nodes(documents["design.sysml"]):
        assert not plantuml_diagram.has_trace_diagram(node_)


def test_diagram_engine_defaults_to_mermaid(tmp_path):
    documents, _, project_config = _read_documents(
        tmp_path,
        {"requirements.sysml": REQUIREMENTS_TEXT, "design.sysml": DESIGN_TEXT},
    )
    document = documents["design.sysml"]

    assert SysMLFormat().diagram_engine == plantuml_diagram.MERMAID_ENGINE
    assert uses_plantuml_diagrams(project_config, document)

    project_config.formats = [*ProjectConfig.default_formats(), SysMLFormat()]
    assert not uses_plantuml_diagrams(project_config, document)


def test_diagram_engine_rejects_unknown_engines():
    with pytest.raises(ValueError, match="diagram_engine must be one of"):
        SysMLFormat(diagram_engine="graphviz")
