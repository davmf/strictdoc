"""
The tracker layout: a tracker file and the folder and item files it
includes are read as one document and written back file by file.
"""

import os
from typing import Dict, List

import pytest

from strictdoc.backend.sdoc.document_reference import DocumentReference
from strictdoc.backend.sdoc.models.node import SDocNode, SDocNodeField
from strictdoc.backend.sysml import node_data, tracker
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.backend.sysml.sysml_format import SysMLFormat
from strictdoc.backend.sysml.writer import SysMLTrackerWriter

FILES: Dict[str, str] = {
    "MODEL.sysml": """\
package 'MODEL' {
    public import 'TRK-SYS';
}
""",
    "TRK-SYS/TRK-SYS.sysml": """\
package 'TRK-SYS' {
    @StrictDocWorkspace::Tracker { title = "System requirements"; kind = "requirements"; prefix = "SYS"; }
    doc /*
     * Requirements of the kettle.
     */

    public import 'SYS-F-HEATING'::*;
    public import 'SYS-F-SAFETY'::*;
}
""",
    "TRK-SYS/SYS-F-HEATING.sysml": """\
package 'SYS-F-HEATING' {
    @StrictDocWorkspace::Folder { title = "Heating"; }
    doc /*
     * Heating element.
     */

    public import 'SYS-001'::*;
    public import 'SYS-002'::*;
}
""",
    "TRK-SYS/SYS-F-SAFETY.sysml": """\
package 'SYS-F-SAFETY' {
    @StrictDocWorkspace::Folder { title = "Safety"; }

    public import 'SYS-010'::*;
}
""",
    "TRK-SYS/SYS-001.sysml": """\
package 'SYS-001' {
    private import ScalarValues::*;
    private import 'TRK-STK'::*;

    requirement <'SYS-001'> 'Boil time' {
        doc /*
         * The kettle shall boil 1 litre in at most 180 s.
         */
        attribute boilTime : Real;
    }

    dependency from 'SYS-001' to 'STK-001';
}
""",
    "TRK-SYS/SYS-002.sysml": """\
package 'SYS-002' {
    private import ScalarValues::*;
    private import 'TRK-STK'::*;

    requirement <'SYS-002'> 'Keep warm' {
        doc /*
         * The kettle shall keep the water above 80 C for 30 min.
         */
    }
}
""",
    "TRK-SYS/SYS-010.sysml": """\
package 'SYS-010' {
    private import ScalarValues::*;
    private import 'TRK-STK'::*;

    requirement <'SYS-010'> 'Dry boil' {
        doc /*
         * The kettle shall switch off within 5 s when it is empty.
         */
    }
}
""",
    "TRK-SC/TRK-SC.sysml": """\
package 'TRK-SC' {
    @StrictDocWorkspace::Tracker { title = "Scenarios"; kind = "design"; prefix = "SC"; }

    public import 'SC-001'::*;
}
""",
    "TRK-SC/SC-001.sysml": """\
package 'SC-001' {
    private import 'TRK-SYS'::*;

    part kettle {
        part element;
    }

    satisfy 'SYS-001' by kettle.element;
    satisfy 'SYS-001' by kettle;
}
""",
}


@pytest.fixture(name="workspace")
def fixture_workspace(tmp_path) -> str:
    for path_, text_ in FILES.items():
        full_path = tmp_path / path_
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(text_, encoding="utf-8")
    return str(tmp_path)


def _read(workspace: str, tracker_id: str = "TRK-SYS"):
    path = os.path.join(workspace, tracker_id, f"{tracker_id}.sysml")
    return SysMLReader.read_from_tracker_file(path, relative_path=path)


def _file_text(workspace: str, relative_path: str) -> str:
    with open(
        os.path.join(workspace, relative_path), encoding="utf-8"
    ) as file_:
        return file_.read()


def _children(container, node_type: str) -> List[SDocNode]:
    return [
        child_
        for child_ in container.section_contents
        if isinstance(child_, SDocNode) and child_.node_type == node_type
    ]


def _uid(node: SDocNode) -> str:
    return node.ordered_fields_lookup["UID"][0].get_text_value()


def _new_requirement(section: SDocNode, title: str) -> SDocNode:
    title_field = SDocNodeField.create_from_string(
        parent=None, field_name="TITLE", field_value=title, multiline=False
    )
    requirement = SDocNode(
        parent=section,
        node_type="REQUIREMENT",
        fields=[title_field],
        relations=[],
    )
    title_field.parent = requirement
    requirement.ng_document_reference = section.ng_document_reference
    requirement.ng_including_document_reference = DocumentReference()
    return requirement


def test_01_only_tracker_files_are_documents(workspace):
    format_ = SysMLFormat(tracker_layout=True)
    assert format_.is_document_file(
        os.path.join(workspace, "TRK-SYS", "TRK-SYS.sysml")
    )
    for path_ in ("MODEL.sysml", "TRK-SYS/SYS-001.sysml"):
        assert not format_.is_document_file(os.path.join(workspace, path_))
    assert SysMLFormat().is_document_file(
        os.path.join(workspace, "TRK-SYS", "SYS-001.sysml")
    )


def test_02_tracker_is_read_as_one_document(workspace):
    document = _read(workspace)
    assert document.title == "System requirements"
    assert not document.autogen
    sections = _children(document, "SECTION")
    assert [
        section_.ordered_fields_lookup["TITLE"][0].get_text_value()
        for section_ in sections
    ] == ["Heating", "Safety"]
    assert [_uid(node_) for node_ in _children(sections[0], "REQUIREMENT")] == [
        "SYS-001",
        "SYS-002",
    ]
    requirement = _children(sections[0], "REQUIREMENT")[0]
    item_file = node_data.get_item_file(requirement)
    assert item_file is not None
    assert item_file.file_path.endswith("SYS-001.sysml")
    assert requirement.relations[0].ref_uid == "STK-001"
    folder = node_data.get_folder(sections[0])
    assert folder is not None and folder.file_id == "SYS-F-HEATING"
    tracker_data = node_data.get_tracker(document)
    assert tracker_data is not None
    assert len(tracker_data.file_paths) == 6


def test_03_writing_an_unchanged_tracker_writes_nothing(workspace):
    document = _read(workspace)
    assert SysMLTrackerWriter.write_to_files(document) == []
    for path_, text_ in FILES.items():
        assert _file_text(workspace, path_) == text_


def test_04_an_edit_rewrites_the_item_file_only(workspace):
    document = _read(workspace)
    requirement = _children(_children(document, "SECTION")[0], "REQUIREMENT")[1]
    requirement.set_field_value(
        field_name="STATEMENT", form_field_index=0, value="Changed text."
    )
    changed = SysMLTrackerWriter.write_to_files(document)
    assert [os.path.basename(path_) for path_ in changed] == ["SYS-002.sysml"]
    assert "Changed text." in _file_text(workspace, "TRK-SYS/SYS-002.sysml")


def test_05_a_new_requirement_gets_an_id_a_file_and_an_include(workspace):
    document = _read(workspace)
    safety = _children(document, "SECTION")[1]
    safety.section_contents.append(_new_requirement(safety, "Lid lock"))
    changed = SysMLTrackerWriter.write_to_files(document)
    assert sorted(os.path.basename(path_) for path_ in changed) == [
        "SYS-011.sysml",
        "SYS-F-SAFETY.sysml",
    ]
    assert _file_text(workspace, "TRK-SYS/SYS-011.sysml") == (
        "package 'SYS-011' {\n"
        "    private import ScalarValues::*;\n"
        "    private import 'TRK-STK'::*;\n"
        "\n"
        "    requirement <'SYS-011'> 'Lid lock' {\n"
        "    }\n"
        "}\n"
    )
    assert "    public import 'SYS-011'::*;\n" in _file_text(
        workspace, "TRK-SYS/SYS-F-SAFETY.sysml"
    )
    # A second save knows the new file and changes nothing.
    assert SysMLTrackerWriter.write_to_files(document) == []


def test_06_a_deleted_requirement_loses_its_file_and_include(workspace):
    document = _read(workspace)
    heating = _children(document, "SECTION")[0]
    heating.section_contents.remove(_children(heating, "REQUIREMENT")[1])
    SysMLTrackerWriter.write_to_files(document)
    assert not os.path.exists(os.path.join(workspace, "TRK-SYS/SYS-002.sysml"))
    assert "SYS-002" not in _file_text(workspace, "TRK-SYS/SYS-F-HEATING.sysml")


def test_07_a_moved_requirement_changes_the_includes_only(workspace):
    document = _read(workspace)
    heating, safety = _children(document, "SECTION")
    moved = _children(heating, "REQUIREMENT")[1]
    heating.section_contents.remove(moved)
    safety.section_contents.append(moved)
    changed = SysMLTrackerWriter.write_to_files(document)
    assert sorted(os.path.basename(path_) for path_ in changed) == [
        "SYS-F-HEATING.sysml",
        "SYS-F-SAFETY.sysml",
    ]
    assert (
        _file_text(workspace, "TRK-SYS/SYS-002.sysml")
        == (FILES["TRK-SYS/SYS-002.sysml"])
    )


def test_08_a_new_section_gets_a_folder_file(workspace):
    document = _read(workspace)
    section = SDocNode.create_section(document, document, "Water level")
    section.ng_including_document_reference = DocumentReference()
    section.ng_document_reference = DocumentReference()
    section.ng_document_reference.set_document(document)
    document.section_contents.append(section)
    SysMLTrackerWriter.write_to_files(document)
    assert _file_text(workspace, "TRK-SYS/SYS-F-WATER-LEVEL.sysml") == (
        "package 'SYS-F-WATER-LEVEL' {\n"
        '    @StrictDocWorkspace::Folder { title = "Water level"; }\n'
        "}\n"
    )
    assert "public import 'SYS-F-WATER-LEVEL'::*;" in _file_text(
        workspace, "TRK-SYS/TRK-SYS.sysml"
    )


def test_09_design_items_use_their_item_id_as_uid(workspace):
    document = _read(workspace, "TRK-SC")
    assert document.autogen
    part = _children(document, "PART")[0]
    assert _uid(part) == "SC-001"
    item_file = node_data.get_item_file(part)
    assert item_file is not None and item_file.file_id == "SC-001"
    # Two satisfy statements that resolve to the same node give one relation.
    assert [
        (relation_.ref_uid, relation_.role) for relation_ in part.relations
    ] == [("SYS-001", "Satisfies")]


@pytest.mark.parametrize(
    "file_path, text, message",
    [
        (
            "TRK-SYS/SYS-F-SAFETY.sysml",
            (
                "package 'SYS-F-SAFETY' {\n"
                '    @StrictDocWorkspace::Folder { title = "Safety"; }\n'
                "    public import 'SYS-404'::*;\n}\n"
            ),
            "'SYS-404' names no file",
        ),
        (
            "TRK-SYS/SYS-F-SAFETY.sysml",
            (
                "package 'SYS-F-SAFETY' {\n"
                '    @StrictDocWorkspace::Folder { title = "Safety"; }\n'
                "    public import 'SYS-F-HEATING'::*;\n}\n"
            ),
            "'SYS-F-HEATING' is included more than once",
        ),
        (
            "TRK-SYS/SYS-F-SAFETY.sysml",
            (
                "package 'SYS-F-SAFETY' {\n"
                '    @StrictDocWorkspace::Folder { title = "Safety"; }\n'
                "    public import 'SYS-F-SAFETY'::*;\n}\n"
            ),
            "'SYS-F-SAFETY' includes itself",
        ),
        (
            "TRK-SYS/SYS-010.sysml",
            "package 'SYS-999' {\n}\n",
            "the top-level package is 'SYS-999', expected 'SYS-010'",
        ),
    ],
)
def test_10_errors_name_the_file(workspace, file_path, text, message):
    with open(
        os.path.join(workspace, file_path), "w", encoding="utf-8"
    ) as file_:
        file_.write(text)
    with pytest.raises(tracker.TrackerError) as exception_info:
        _read(workspace)
    assert message in exception_info.value.to_print_message()
