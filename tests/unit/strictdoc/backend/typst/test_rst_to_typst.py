import os
from pathlib import Path

from strictdoc.backend.typst.rst_to_typst import RstToTypstConverter


def create_converter(path_to_output_dir: str = "/nonexistent"):
    return RstToTypstConverter(
        path_to_output_dir=path_to_output_dir,
        render_link=lambda uid_: f"<link {uid_}>",
        render_anchor=lambda uid_: f"<anchor {uid_}>",
        diagram_name_prefix="doc",
    )


def test_001_inline_markup():
    converter = create_converter()
    output = converter.convert(
        "**bold** *emph* ``code`` `site <https://example.com>`_"
    )
    assert output == (
        '#strong[bold] #emph[emph] #raw("code") '
        '#link("https://example.com")[site]'
    )
    assert converter.warnings == []


def test_002_inline_conversion_of_one_paragraph_has_no_paragraph_break():
    converter = create_converter()
    assert converter.convert_inline("*T*") == "#emph[T]"


def test_003_lists():
    converter = create_converter()
    output = converter.convert("- one\n- two\n\n#. a\n#. b\n")
    assert output == ('#list([one], [two])\n\n#enum(numbering: "1.", [a], [b])')


def test_004_rst_backslash_escape_leaves_no_character():
    converter = create_converter()
    assert converter.convert("a\\ b") == "ab"


def test_005_list_table_with_header_and_caption():
    converter = create_converter()
    output = converter.convert(
        """\
.. list-table:: Levels
   :header-rows: 1

   * - A
     - B
   * - 1
     - 2
"""
    )
    assert output == (
        "#figure(table(\n"
        "  columns: (50fr, 50fr,),\n"
        "  table.header([A], [B]),\n"
        "  [1],\n"
        "  [2],\n"
        "), caption: [Levels])"
    )


def test_006_code_block_keeps_language_unless_kroki_would_draw_it():
    converter = create_converter()
    assert (
        converter.convert(".. code-block:: c\n\n   int x;\n")
        == '#raw(block: true, lang: "c", "int x;")'
    )
    assert (
        converter.convert(".. code-block:: plantuml\n\n   @startuml\n")
        == '#raw(block: true, "@startuml")'
    )


def test_007_mermaid_raw_html_becomes_named_fenced_block():
    converter = create_converter()
    output = converter.convert(
        """\
.. raw:: html

    <pre class="mermaid">
    graph TD
    A --&gt; B
    </pre>
"""
    )
    assert output == (
        "```mermaid\n"
        '%%{init: {"htmlLabels": false, "fontFamily": "DejaVu Sans Mono", '
        '"flowchart": {"htmlLabels": false}}}%%\n'
        "%% mermaid-name: doc-diagram-1\n"
        "graph TD\n"
        "A --> B\n"
        "```"
    )
    assert converter.has_diagrams


def test_008_plantuml_raw_html_gets_a_diagram_name():
    converter = create_converter()
    output = converter.convert(
        """\
.. raw:: html

    <pre class="plantuml">
    @startuml
    Alice -> Bob
    @enduml
    </pre>
"""
    )
    assert output == (
        "```plantuml\n@startuml doc-diagram-1\nAlice -> Bob\n@enduml\n```"
    )


def test_009_other_raw_html_is_dropped_with_a_warning():
    converter = create_converter()
    assert converter.convert(".. raw:: html\n\n   <b>x</b>\n") == ""
    assert converter.warnings == ["Raw html content is not written to Typst."]


def test_010_collapsible_section_html_is_dropped_without_a_warning():
    converter = create_converter()
    output = converter.convert(
        """\
.. raw:: html

    <details><summary>Show source</summary>

Body

.. raw:: html

    </details>
"""
    )
    assert output == "Body"
    assert converter.warnings == []


def test_011_raw_typst_is_passed_through():
    converter = create_converter()
    assert (
        converter.convert(".. raw:: typst\n\n   #pagebreak()\n")
        == "#pagebreak()"
    )


def test_012_strictdoc_links_and_anchors():
    converter = create_converter()
    output = converter.convert(
        "See :strictdoc-typst-link:`REQ-1`.\n\n:strictdoc-typst-anchor:`A-1`\n"
    )
    assert output == "See <link REQ-1>.\n\n<anchor A-1>"


def test_013_admonition():
    converter = create_converter()
    assert (
        converter.convert(".. note::\n\n   Text.\n")
        == "#sd-admonition([Note])[Text.]"
    )


def test_014_image_found_and_missing(tmp_path: Path):
    converter = create_converter(str(tmp_path))
    os.makedirs(tmp_path / "_assets")
    (tmp_path / "_assets" / "a.png").write_bytes(b"")
    assert (
        converter.convert(".. image:: _assets/a.png\n   :width: 50%\n")
        == '#image("_assets/a.png", width: 50%)'
    )
    assert (
        converter.convert(".. image:: _assets/b.png\n")
        == '#sd-missing-image("_assets/b.png")'
    )
    assert converter.warnings == ["Image not found: _assets/b.png"]


def test_015_image_of_nested_document_is_rebased_to_flat_assets(
    tmp_path: Path,
):
    converter = create_converter(str(tmp_path))
    os.makedirs(tmp_path / "_assets")
    (tmp_path / "_assets" / "a.png").write_bytes(b"")
    assert (
        converter.convert(".. image:: ../_assets/a.png\n")
        == '#image("_assets/a.png")'
    )


def test_016_footnote():
    converter = create_converter()
    assert (
        converter.convert("Text [#]_.\n\n.. [#] The note.\n")
        == "Text #footnote[The note.]."
    )


def test_017_mermaid_shape_nodes_become_classic_nodes():
    converter = create_converter()
    output = converter.convert(
        """\
.. raw:: html

    <pre class="mermaid">
    flowchart LR
      n18@{ shape: diam, label: "bubble1" }
      n33@{ shape: fork }
      n18 --&gt; n33
    </pre>
"""
    )
    assert output.splitlines()[3:] == [
        "flowchart LR",
        '  n18{"bubble1"}',
        '  n33[" "]',
        "  n18 --> n33",
        "  style n33 fill:#333,stroke:#333",
        "```",
    ]
