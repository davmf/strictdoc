from strictdoc.backend.sysml.diagram import as_rst_raw_html, diagram_options
from strictdoc.backend.sysml.reader import SysMLReader


def test_01_requirements_documents_draw_their_traces():
    assert diagram_options("TRK-SYS", is_design=False) == (
        "view=requirements root=TRK-SYS depth=1 orientation=horizontal text=false links=/?a={id}"
    )


def test_02_design_documents_draw_their_definitions():
    assert diagram_options("Design", is_design=True) == (
        "view=definitions root=Design"
    )


def test_03_a_root_with_spaces_is_quoted():
    assert diagram_options("System requirements", is_design=True) == (
        'view=definitions root="System requirements"'
    )


def test_04_the_placeholder_loads_the_script_from_the_static_folder():
    assert as_rst_raw_html('view=definitions root="A b"', "assets/") == (
        ".. raw:: html\n"
        "\n"
        '    <div class="sysml-diagram" data-sysml-document="true"'
        ' data-sysml-options="view=definitions root=&quot;A b&quot;"></div>\n'
        '    <script type="module"'
        ' src="/assets/plantuml/sysml/sysml-diagrams.js"></script>'
    )


def test_04b_a_tracker_links_to_the_workspace():
    assert as_rst_raw_html(
        "view=definitions root=TRK-HW", "_static", workspace_item="TRK-HW"
    ).splitlines()[2] == (
        '    <p class="sysml-diagram-workspace">'
        '<a href="/workspace?item=TRK-HW">Open in workspace</a></p>'
    )


def test_05_the_diagram_node_is_the_first_node_of_a_document():
    document = SysMLReader.read_from_string(
        "package Design {\n    part def Pump;\n}\n",
        file_path=None,
        relative_path="design.sysml",
    )
    statement = (
        document.section_contents[0]
        .ordered_fields_lookup["STATEMENT"][0]
        .get_text_value()
    )
    assert 'data-sysml-options="view=definitions root=Design"' in statement


def test_06_a_file_without_one_package_has_no_diagram():
    document = SysMLReader.read_from_string(
        "part def Pump;\npart def Valve;\n",
        file_path=None,
        relative_path="design.sysml",
    )
    assert all(
        "sysml-diagram" not in str(node_.ordered_fields_lookup)
        for node_ in document.section_contents
    )
