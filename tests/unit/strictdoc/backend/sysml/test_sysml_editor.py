from typing import Dict, List

import pytest

from strictdoc.backend.sysml import editor, node_data
from strictdoc.backend.sysml.editor import (
    NEW_ROW_ID,
    SysMLEditError,
    SysMLTableRow,
)
from strictdoc.backend.sysml.model import SysMLElement
from strictdoc.backend.sysml.parser import SysMLParser
from strictdoc.backend.sysml.reader import SysMLReader

DESIGN_TEXT = """\
package 'Design' {
    // A line note that is kept.
    part def Pump {
        doc /*
         * The pump moves sample into the chip.
         */
        attribute flowRate : Real = 2;
        satisfy 'SYS-THR-001' by pump;
        part pump : Pump;
    }

    #safety part def Valve;

    part def Chip { }
}
"""


def _element(text: str, name: str) -> SysMLElement:
    model = SysMLParser.parse_string(text)
    for member_ in model.members[0].members:
        if isinstance(member_, SysMLElement) and member_.name == name:
            assert member_.member_span is not None
            found = editor.find_element(model, member_.member_span.byte_start)
            assert found is not None
            return found
    raise AssertionError(name)


def _rows(element: SysMLElement) -> List[SysMLTableRow]:
    return [
        SysMLTableRow(row_id=str(index_), values=editor.member_values(member_))
        for index_, member_ in enumerate(editor.editable_members(element))
    ]


def _new_row(**values: str) -> SysMLTableRow:
    row_values: Dict[str, str] = dict.fromkeys(editor.MEMBERS_COLUMNS, "")
    for key_, value_ in values.items():
        row_values[key_.replace("_", " ").capitalize()] = value_
    return SysMLTableRow(row_id=NEW_ROW_ID, values=row_values)


def test_01_details_and_members_mirror_the_tables():
    pump = _element(DESIGN_TEXT, "Pump")

    details = editor.details_values(pump)
    assert details["Kind"] == "part def"
    assert details["Name"] == "Pump"

    rows = _rows(pump)
    assert [row_.values["Name"] for row_ in rows] == ["flowRate", "pump"]
    assert rows[0].values["Kind"] == "attribute"
    assert rows[0].values["Type"] == "Real"
    assert rows[0].values["Value"] == "2"
    assert rows[1].values["Type"] == "Pump"


def test_02_unchanged_form_is_a_no_op():
    pump = _element(DESIGN_TEXT, "Pump")
    result = editor.apply_element_edit(
        DESIGN_TEXT,
        pump,
        details=editor.details_values(pump),
        rows=_rows(pump),
        source=editor.element_source(DESIGN_TEXT, pump),
    )
    assert result is None


def test_03_changed_member_row_rewrites_only_its_declaration():
    pump = _element(DESIGN_TEXT, "Pump")
    rows = _rows(pump)
    rows[0].values["Value"] = "4"
    rows[0].values["Units"] = "l/min"

    result = editor.apply_element_edit(
        DESIGN_TEXT,
        pump,
        details=editor.details_values(pump),
        rows=rows,
        source=editor.element_source(DESIGN_TEXT, pump),
    )

    assert result == DESIGN_TEXT.replace(
        "attribute flowRate : Real = 2;",
        "attribute flowRate : Real = 4 [l/min];",
    )


def test_04_changed_details_rewrite_the_head_and_keep_the_body():
    pump = _element(DESIGN_TEXT, "Pump")
    details = editor.details_values(pump)
    details["Name"] = "Main pump"
    details["Short name"] = "P-1"

    result = editor.apply_table_edits(
        DESIGN_TEXT, pump, details=details, rows=_rows(pump)
    )

    assert result == DESIGN_TEXT.replace(
        "part def Pump {", "part def <'P-1'> 'Main pump' {"
    )


def test_05_deleted_row_removes_the_member_line():
    pump = _element(DESIGN_TEXT, "Pump")
    rows = _rows(pump)
    rows[1].is_deleted = True

    result = editor.apply_table_edits(
        DESIGN_TEXT, pump, details=editor.details_values(pump), rows=rows
    )

    assert result == DESIGN_TEXT.replace("        part pump : Pump;\n", "")


def test_06_new_row_is_inserted_before_the_closing_brace():
    pump = _element(DESIGN_TEXT, "Pump")
    rows = _rows(pump) + [_new_row(kind="part", name="valve", type="Valve")]

    result = editor.apply_table_edits(
        DESIGN_TEXT, pump, details=editor.details_values(pump), rows=rows
    )

    assert result == DESIGN_TEXT.replace(
        "        part pump : Pump;\n",
        "        part pump : Pump;\n        part valve : Valve;\n",
    )


def test_07_new_row_gives_an_element_without_body_a_body():
    valve = _element(DESIGN_TEXT, "Valve")
    rows = [_new_row(kind="attribute", name="diameter", type="Real")]

    result = editor.apply_table_edits(
        DESIGN_TEXT, valve, details=editor.details_values(valve), rows=rows
    )

    assert result == DESIGN_TEXT.replace(
        "    #safety part def Valve;\n",
        "    #safety part def Valve {\n"
        "        attribute diameter : Real;\n"
        "    }\n",
    )


def test_08_new_row_in_a_one_line_body():
    chip = _element(DESIGN_TEXT, "Chip")
    rows = [_new_row(kind="part", name="well", type="Well", multiplicity="24")]

    result = editor.apply_table_edits(
        DESIGN_TEXT, chip, details=editor.details_values(chip), rows=rows
    )

    assert result == DESIGN_TEXT.replace(
        "    part def Chip { }\n",
        "    part def Chip {\n        part well : Well [24];\n    }\n",
    )


def test_09_annotations_are_kept_and_editable_in_details():
    valve = _element(DESIGN_TEXT, "Valve")
    details = editor.details_values(valve)
    assert details["Annotations"] == "safety"

    details["Annotations"] = "safety critical"
    result = editor.apply_table_edits(
        DESIGN_TEXT, valve, details=details, rows=[]
    )

    assert result == DESIGN_TEXT.replace(
        "#safety part def Valve;", "#safety #critical part def Valve;"
    )


def test_10_source_edit_replaces_the_element_and_keeps_indentation():
    pump = _element(DESIGN_TEXT, "Pump")
    source = editor.element_source(DESIGN_TEXT, pump)
    assert source.startswith("part def Pump {\n    doc /*\n")
    assert source.endswith("\n    part pump : Pump;\n}")

    result = editor.apply_element_edit(
        DESIGN_TEXT,
        pump,
        details=editor.details_values(pump),
        rows=_rows(pump),
        source=source.replace("Real = 2", "Real = 3"),
    )

    assert result == DESIGN_TEXT.replace("Real = 2", "Real = 3")


def test_11_source_with_more_than_one_element_is_rejected():
    pump = _element(DESIGN_TEXT, "Pump")
    with pytest.raises(SysMLEditError, match="exactly one SysML element"):
        editor.apply_source_edit(DESIGN_TEXT, pump, "part def A;\npart def B;")


def test_12_source_with_a_syntax_error_is_rejected():
    pump = _element(DESIGN_TEXT, "Pump")
    with pytest.raises(SysMLEditError, match="Could not parse SysML file"):
        editor.apply_source_edit(DESIGN_TEXT, pump, "part def Pump {")


def test_13_tables_and_source_changed_together_are_rejected():
    pump = _element(DESIGN_TEXT, "Pump")
    details = editor.details_values(pump)
    details["Name"] = "Other"
    with pytest.raises(SysMLEditError, match="not both"):
        editor.apply_element_edit(
            DESIGN_TEXT,
            pump,
            details=details,
            rows=_rows(pump),
            source="part def Pump;",
        )


def test_14_unknown_kind_and_modifier_are_rejected():
    pump = _element(DESIGN_TEXT, "Pump")
    with pytest.raises(SysMLEditError, match="Unknown kind 'widget'"):
        editor.apply_table_edits(
            DESIGN_TEXT,
            pump,
            details=editor.details_values(pump),
            rows=[_new_row(kind="widget", name="w")],
        )
    with pytest.raises(SysMLEditError, match="Unknown modifier 'fast'"):
        editor.apply_table_edits(
            DESIGN_TEXT,
            pump,
            details=editor.details_values(pump),
            rows=[_new_row(kind="part", modifiers="fast", name="w")],
        )


def test_15_units_without_a_value_are_rejected():
    pump = _element(DESIGN_TEXT, "Pump")
    rows = _rows(pump)
    rows[0].values["Value"] = ""
    rows[0].values["Units"] = "s"
    with pytest.raises(SysMLEditError, match="need a value"):
        editor.apply_table_edits(
            DESIGN_TEXT, pump, details=editor.details_values(pump), rows=rows
        )


def test_16_names_are_quoted_when_needed():
    pump = _element(DESIGN_TEXT, "Pump")
    rows = _rows(pump) + [
        _new_row(kind="part", name="part", type="Pump"),
        _new_row(kind="part", name="it's", type="Pump"),
    ]
    result = editor.apply_table_edits(
        DESIGN_TEXT, pump, details=editor.details_values(pump), rows=rows
    )
    assert "part 'part' : Pump;" in result
    assert "part 'it\\'s' : Pump;" in result


def test_17_blank_new_rows_are_ignored():
    pump = _element(DESIGN_TEXT, "Pump")
    assert not editor.tables_changed(
        pump, editor.details_values(pump), _rows(pump) + [_new_row()]
    )


def test_18_validate_text_reports_reader_errors():
    text = "package 'Design' {\n    part def A;\n    verify 'R-1';\n}\n"
    with pytest.raises(
        SysMLEditError, match="statement must be inside an element"
    ):
        editor.validate_text(text, file_path=None, relative_path="d.sysml")


def test_19_normalize_source_handles_browser_text():
    assert (
        editor.normalize_source("\r\n  a\u00a0b  \r\n\r\nc\n\n") == "  a b\n\nc"
    )


def test_20_reader_stores_offsets_for_the_editor():
    document = SysMLReader.read_from_string(
        DESIGN_TEXT, file_path=None, relative_path="design.sysml"
    )
    assert node_data.is_design_document(document)
    assert node_data.get_source_hash(document) == node_data.source_hash(
        DESIGN_TEXT
    )

    pump_node = document.section_contents[0]
    assert node_data.is_design_element_node(pump_node)
    model = SysMLParser.parse_string(DESIGN_TEXT)
    offset = node_data.get_member_offset(pump_node)
    assert offset is not None
    element = editor.find_element(model, offset)
    assert element is not None and element.name == "Pump"


def test_21_requirements_documents_are_not_design_documents():
    text = (
        "package 'Requirements' {\n"
        "    requirement <'R-1'> 'Title' {\n"
        "        doc /*\n"
        "         * Statement.\n"
        "         */\n"
        "    }\n"
        "}\n"
    )
    document = SysMLReader.read_from_string(
        text, file_path=None, relative_path="requirements.sysml"
    )
    assert not node_data.is_design_document(document)
