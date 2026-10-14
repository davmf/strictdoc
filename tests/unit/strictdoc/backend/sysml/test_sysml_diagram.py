from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sysml import node_data
from strictdoc.backend.sysml.diagram import (
    as_rst_raw_html,
    create_mermaid_diagram,
)
from strictdoc.backend.sysml.parser import SysMLParser
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.backend.sysml.sysml_format import SysMLFormat
from strictdoc.backend.sysml.writer import SysMLWriter
from strictdoc.core.document_meta import DocumentMeta
from strictdoc.helpers.paths import SDocRelativePath

REQUIREMENTS_TEXT = """\
package 'System' {
    package 'Throughput' {
        requirement <'SYS-1'> 'Shift throughput' {
            attribute required : Real = 96;
        }

        requirement <'SYS-2'> 'Utilisation' {
        }

        #derivation dependency from 'SYS-1' to 'STK-1';
        dependency from 'SYS-2' to 'SYS-1';
    }
}
"""

DESIGN_TEXT = """\
package 'Design' {
    part def Heater {
        attribute maxTemperature : Real = 100;
    }

    part def <'HW-STN'> Station :> Resource {
        part heater : Heater;
        satisfy 'SYS-1' by heater;
    }

    action def Run {
        action load;
        action heat;
        decide check;
        first start then load;
        first load then heat;
        first heat then check;
        first check if temperature > 90 then done;
    }

    verification def Check {
        objective {
            verify 'SYS-2';
        }
    }

    satisfy 'SYS-3' by other.station;
}
"""


def _diagram(text: str) -> str:
    diagram = create_mermaid_diagram(SysMLParser.parse_string(text))
    assert diagram is not None
    return diagram


def test_01_requirements_are_drawn_inside_their_packages():
    diagram = _diagram(REQUIREMENTS_TEXT)
    assert diagram.splitlines() == [
        '%%{init: {"flowchart": {"wrappingWidth": 400}}}%%',
        "flowchart LR",
        # The top-level package is the document and has no box.
        '  subgraph n1["«package»#160;Throughput"]',
        "    n2(\"«requirement»<br/>#lt;'SYS-1'#gt; Shift throughput\")",
        "    n3(\"«requirement»<br/>#lt;'SYS-2'#gt; Utilisation\")",
        "  end",
        '  n4("«requirement»<br/>STK-1")',
        '  n2 -.->|"«derive»"| n4',
        '  n3 -.->|"«dependency»"| n2',
        "  classDef external stroke-dasharray: 5 5",
        "  class n4 external",
    ]


def test_02_design_elements_flows_and_trace_links_are_drawn():
    diagram = _diagram(DESIGN_TEXT)
    assert diagram.splitlines() == [
        '%%{init: {"flowchart": {"wrappingWidth": 400}}}%%',
        "flowchart LR",
        # A definition has square corners and lists its attributes.
        '  n1["«part def»<br/>Heater<br/>maxTemperature : Real = 100"]',
        # An element with members nests them under a one-line title. The
        # declaration is in a compartment box.
        '  subgraph n2["«part#160;def»#160;Station"]',
        "    n2c[\"#lt;'HW-STN'#gt; Station :#gt; Resource\"]",
        # A usage has rounded corners.
        '    n3("«part»<br/>heater : Heater")',
        "  end",
        '  subgraph n4["«action#160;def»#160;Run"]',
        '    n5("«action»<br/>load")',
        '    n6("«action»<br/>heat")',
        '    n7@{ shape: diam, label: "check" }',
        "    n8@{ shape: sm-circ }",
        "    n9@{ shape: fr-circ }",
        "  end",
        # The objective is not drawn.
        '  n10["«verification def»<br/>Check"]',
        # References that are not in the file.
        '  n11("«requirement»<br/>SYS-1")',
        '  n12("«requirement»<br/>SYS-2")',
        '  n13("other.station")',
        '  n14("«requirement»<br/>SYS-3")',
        '  n3 -.->|"«satisfy»"| n11',
        "  n8 --> n5",
        "  n5 --> n6",
        "  n6 --> n7",
        '  n7 -->|"[temperature #gt; 90]"| n9',
        # The verify arrow of the objective starts at its owner.
        '  n10 -.->|"«verify»"| n12',
        '  n13 -.->|"«satisfy»"| n14',
        '  n3 -.->|"«defined by»"| n1',
        "  classDef external stroke-dasharray: 5 5",
        "  class n11,n12,n13,n14 external",
    ]


def test_03_file_with_nothing_to_draw_has_no_diagram():
    model = SysMLParser.parse_string("// Only a note.\n")
    assert create_mermaid_diagram(model) is None
    model = SysMLParser.parse_string("package 'Empty' {\n}\n")
    assert create_mermaid_diagram(model) is None


def test_04_raw_html_escapes_the_diagram_source():
    raw_html = as_rst_raw_html('flowchart LR\n  n1("a<br/>b") --> n2')
    assert raw_html == (
        ".. raw:: html\n"
        "\n"
        '    <pre class="mermaid">\n'
        "    flowchart LR\n"
        '      n1("a&lt;br/&gt;b") --&gt; n2\n'
        "    </pre>"
    )


def test_05_reader_puts_the_diagram_first_and_writer_skips_it():
    document = SysMLReader.read_from_string(
        REQUIREMENTS_TEXT, file_path="t.sysml", relative_path="t.sysml"
    )
    diagram_node = document.section_contents[0]
    assert isinstance(diagram_node, SDocNode)
    assert diagram_node.node_type == "TEXT"
    assert diagram_node.autogen
    assert node_data.is_diagram(diagram_node)
    statement = diagram_node.get_field_by_name("STATEMENT").get_text_value()
    assert statement.startswith('.. raw:: html\n\n    <pre class="mermaid">')
    assert "pre" not in SysMLWriter.write(document)


def test_06_design_document_starts_with_the_diagram():
    document = SysMLReader.read_from_string(
        DESIGN_TEXT, file_path="t.sysml", relative_path="t.sysml"
    )
    assert node_data.is_diagram(document.section_contents[0])


def test_07_saving_a_document_rebuilds_the_diagram(tmp_path):
    path_to_file = tmp_path / "system.sysml"
    path_to_file.write_text(REQUIREMENTS_TEXT, encoding="utf8")
    document = SysMLReader.read_from_string(
        REQUIREMENTS_TEXT,
        file_path=str(path_to_file),
        relative_path="system.sysml",
    )
    document.meta = DocumentMeta(
        level=0,
        file_tree_mount_folder="NOT_RELEVANT",
        document_filename="system.sysml",
        document_filename_base="system",
        input_doc_full_path=str(path_to_file),
        input_doc_rel_path=SDocRelativePath("system.sysml"),
        input_doc_dir_rel_path=SDocRelativePath(""),
        input_doc_assets_dir_rel_path=SDocRelativePath("_assets"),
        output_document_dir_full_path="NOT_RELEVANT",
        output_document_dir_rel_path=SDocRelativePath("FIXME"),
    )
    diagram_node = document.section_contents[0]
    old_field = diagram_node.get_field_by_name("STATEMENT")

    # Rename the section, as the web UI does when a section title is edited.
    section = document.section_contents[1]
    section.set_field_value(
        field_name="TITLE", form_field_index=0, value="Capacity"
    )
    SysMLFormat().write_document_to_file(document, project_config=None)

    assert document.section_contents[0] is diagram_node
    new_field = diagram_node.get_field_by_name("STATEMENT")
    assert new_field is not old_field
    assert "Capacity" in new_field.get_text_value()
    assert "Throughput" not in new_field.get_text_value()
