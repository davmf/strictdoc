"""
tracker_convert: a model of one file per document becomes the tracker
layout, and StrictDoc reads the same documents from it.
"""

import os
from typing import Dict, List

import pytest

from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sysml import tracker_convert
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.backend.sysml.tracker_convert import ConversionError, convert
from strictdoc.backend.sysml.writer import SysMLTrackerWriter
from strictdoc.core.document_iterator import SDocDocumentIterator

STAKEHOLDER_TEXT = """\
package 'Stakeholder requirements' {
    doc /*
     * What the user needs.
     */

    private import ScalarValues::*;

    requirement <'STK-001'> 'Hot water' {
        doc /*
         * The user needs boiling water within 3 minutes.
         */
    }
}
"""

SYSTEM_TEXT = """\
package 'System requirements' {
    doc /*
     * Requirements of the kettle.
     */

    private import ScalarValues::*;
    private import 'Stakeholder requirements'::**;

    package 'Heating' {
        doc /*
         * Heating element.
         */

        // The boil time is measured by the verification case.
        requirement <'SYS-001'> 'Boil time' {
            doc /*
             * The kettle shall boil 1 l of water within 180 s.
             */
            attribute requiredSeconds : Real = 180;
        }

        requirement <'SYS-002'> 'Power' {
            doc /*
             * The kettle shall draw at most 2.2 kW.
             */
        }

        dependency from 'SYS-001' to 'STK-001';
        dependency from 'SYS-002' to 'STK-001';
    }
}
"""

DESIGN_TEXT = """\
package KettleDesign {
    doc /*
     * The parts of the kettle.
     */

    private import 'System requirements'::**;

    part def Heater {
        attribute power : Real = 2200;
    }

    part def <'KD-CTRL'> Controller;

    part heater : Heater;

    satisfy 'SYS-002' by heater;
}
"""

VERIFICATION_TEXT = """\
package KettleVerification {
    private import KettleDesign::*;
    private import 'System requirements'::**;

    satisfy 'SYS-001' by heater;

    verification boilTime {
        objective { verify 'SYS-001'; }
    }
}
"""

SOURCES: Dict[str, str] = {
    "requirements/stakeholder.sysml": STAKEHOLDER_TEXT,
    "requirements/system.sysml": SYSTEM_TEXT,
    "design/design.sysml": DESIGN_TEXT,
    "design/verification.sysml": VERIFICATION_TEXT,
    "library/Lib.sysml": "library package Lib {\n}\n",
}

OVERRIDES = {
    "requirements/stakeholder.sysml": {"prefix": "STK"},
    "requirements/system.sysml": {"prefix": "SYS"},
    "design/design.sysml": {"prefix": "KD"},
    "design/verification.sysml": {"prefix": "VER"},
}


def _convert() -> tracker_convert.ConversionResult:
    return convert(SOURCES, model_title="Kettle", overrides=OVERRIDES)


def _write(directory: str, files: Dict[str, str]) -> None:
    for path_, text_ in files.items():
        full_path = os.path.join(directory, path_)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as file_:
            file_.write(text_)


def _nodes(document) -> List[SDocNode]:
    return [
        node_
        for node_, _ in SDocDocumentIterator(document).all_content(
            print_fragments=True
        )
        if isinstance(node_, SDocNode)
    ]


def _summary(document) -> List[tuple]:
    """Each node as the reader builds it, without its MID and diagram."""
    result = []
    for node_ in _nodes(document):
        fields = tuple(
            (field_.field_name, field_.get_text_value())
            for field_ in node_.enumerate_fields()
            if "sysml-diagram" not in field_.get_text_value()
        )
        relations = tuple(
            (relation_.ref_uid, relation_.role) for relation_ in node_.relations
        )
        result.append((node_.node_type, fields, relations))
    return result


def test_01_requirements_become_a_tracker_with_folders_and_items():
    files = _convert().files
    assert files["TRK-SYS/TRK-SYS.sysml"] == (
        "package 'TRK-SYS' {\n"
        '    @StrictDocWorkspace::Tracker { title = "System requirements"; '
        'kind = "requirements"; prefix = "SYS"; }\n'
        "    doc /*\n"
        "     * Requirements of the kettle.\n"
        "     */\n"
        "\n"
        "    public import 'SYS-F-HEATING'::*;\n"
        "}\n"
    )
    assert files["TRK-SYS/SYS-F-HEATING.sysml"] == (
        "package 'SYS-F-HEATING' {\n"
        '    @StrictDocWorkspace::Folder { title = "Heating"; }\n'
        "    doc /*\n"
        "     * Heating element.\n"
        "     */\n"
        "\n"
        "    public import 'SYS-001'::*;\n"
        "    public import 'SYS-002'::*;\n"
        "}\n"
    )
    # The imports name the trackers, the comment goes with the next
    # element, and the dependency goes with its client.
    assert files["TRK-SYS/SYS-001.sysml"] == (
        "package 'SYS-001' {\n"
        "    private import ScalarValues::*;\n"
        "    private import 'TRK-STK'::**;\n"
        "    private import 'TRK-SYS'::*;\n"
        "\n"
        "    // The boil time is measured by the verification case.\n"
        "    requirement <'SYS-001'> 'Boil time' {\n"
        "        doc /*\n"
        "         * The kettle shall boil 1 l of water within 180 s.\n"
        "         */\n"
        "        attribute requiredSeconds : Real = 180;\n"
        "    }\n"
        "\n"
        "    dependency from 'SYS-001' to 'STK-001';\n"
        "}\n"
    )


def test_02_design_items_satisfy_and_traces():
    result = _convert()
    files = result.files
    # A design element without a short name: <PREFIX>-<name>.
    assert "TRK-KD/KD-Heater.sysml" in files
    assert "TRK-KD/KD-CTRL.sysml" in files
    assert result.renamed_uids["KettleDesign::Heater"] == "KD-Heater"
    # A satisfy of a local element goes with the element...
    assert files["TRK-KD/KD-heater-2.sysml"].endswith(
        "    part heater : Heater;\n\n    satisfy 'SYS-002' by heater;\n}\n"
    )
    # ...and one of an element of another document stays in a trace item.
    assert files["TRK-VER/VER-TRACES.sysml"] == (
        "package 'VER-TRACES' {\n"
        "    private import 'TRK-KD'::*;\n"
        "    private import 'TRK-SYS'::**;\n"
        "    private import 'TRK-VER'::*;\n"
        "\n"
        "    satisfy 'SYS-001' by heater;\n"
        "}\n"
    )
    assert files["TRK-VER/TRK-VER.sysml"].endswith(
        "    public import 'VER-TRACES'::*;\n"
        "    public import 'VER-boilTime'::*;\n"
        "}\n"
    )


def test_03_ids_differ_in_more_than_case():
    # KD-Heater and KD-heater would be one file on Windows and macOS.
    result = _convert()
    files = result.files
    assert result.renamed_uids["KettleDesign::heater"] == "KD-heater-2"
    assert "TRK-KD/KD-heater-2.sysml" in files
    lower_names = [path_.lower() for path_ in files]
    assert len(lower_names) == len(set(lower_names))


def test_04_model_root_libraries_and_kinds():
    result = _convert()
    assert result.files["MODEL.sysml"] == (
        "package 'MODEL' {\n"
        '    @StrictDocWorkspace::Model { title = "Kettle"; }\n'
        "\n"
        "    public import 'TRK-STK';\n"
        "    public import 'TRK-SYS';\n"
        "    public import 'TRK-KD';\n"
        "    public import 'TRK-VER';\n"
        "}\n"
    )
    assert (
        result.files["library/StrictDocWorkspace.sysml"]
        == tracker_convert.WORKSPACE_LIBRARY_TEXT
    )
    assert "library/Lib.sysml" not in result.removed
    assert sorted(result.removed) == sorted(
        path_ for path_ in SOURCES if not path_.startswith("library/")
    )
    kinds = {plan_.tracker_id: plan_.kind for plan_ in result.plans}
    assert kinds == {
        "TRK-STK": "requirements",
        "TRK-SYS": "requirements",
        "TRK-KD": "design",
        "TRK-VER": "test cases",
    }


def test_05_strictdoc_reads_the_same_documents(tmp_path):
    result = _convert()
    _write(str(tmp_path), result.files)
    renamed = dict(result.renamed_uids)
    for plan_ in result.plans:
        before = SysMLReader.read_from_string(
            SOURCES[plan_.source_path],
            file_path=plan_.source_path,
            relative_path=plan_.source_path,
        )
        tracker_path = os.path.join(
            str(tmp_path), plan_.tracker_id, f"{plan_.tracker_id}.sysml"
        )
        after = SysMLReader.read_from_tracker_file(
            tracker_path, relative_path=tracker_path
        )
        assert after.title == before.title
        expected = [
            (
                node_type_,
                tuple(
                    (name_, renamed.get(value_, value_))
                    for name_, value_ in fields_
                ),
                relations_,
            )
            for node_type_, fields_, relations_ in _summary(before)
        ]
        assert _summary(after) == expected, plan_.tracker_id


def test_06_the_writer_writes_the_requirements_trackers_as_they_are(
    tmp_path,
):
    # The writer drops line notes, as it does for one file per document.
    sources = dict(SOURCES)
    sources["requirements/system.sysml"] = SYSTEM_TEXT.replace(
        "        // The boil time is measured by the verification case.\n", ""
    )
    result = convert(sources, model_title="Kettle", overrides=OVERRIDES)
    _write(str(tmp_path), result.files)
    for tracker_id_ in ("TRK-STK", "TRK-SYS"):
        path = os.path.join(str(tmp_path), tracker_id_, f"{tracker_id_}.sysml")
        document = SysMLReader.read_from_tracker_file(path, relative_path=path)
        for file_path_, text_ in SysMLTrackerWriter.render(document).items():
            with open(file_path_, encoding="utf-8") as file_:
                assert file_.read() == text_, file_path_


def test_07_tracker_ids_of_converted_packages_name_existing_trackers():
    result = convert(
        {"requirements/system.sysml": SYSTEM_TEXT},
        model_title="Kettle",
        overrides={"requirements/system.sysml": {"prefix": "SYS"}},
        tracker_ids={"Stakeholder requirements": "TRK-STK"},
    )
    assert (
        "    private import 'TRK-STK'::**;\n"
        in (result.files["TRK-SYS/SYS-002.sysml"])
    )


@pytest.mark.parametrize(
    "text,message",
    [
        (
            "package P {\n    doc /* One. */\n    doc /* Two. */\n}\n",
            "only the first doc comment of a package can be converted",
        ),
        (
            (
                "package P {\n    requirement <'R-1'> 'A';\n"
                "    dependency from 'R-9' to 'R-1';\n}\n"
            ),
            "a trace starts from an element that is not in this document",
        ),
        (
            "package P {\n    package <'S-1'> Section {\n    }\n}\n",
            "a package with a short name cannot become a folder",
        ),
        (
            "package P {\n}\npackage Q {\n}\n",
            "must hold one top-level package",
        ),
    ],
)
def test_08_what_cannot_be_converted_is_an_error(text, message):
    with pytest.raises(ConversionError) as exception_info:
        convert({"p.sysml": text}, model_title="M")
    assert message in str(exception_info.value)


def test_09_images_move_with_their_document():
    sources = dict(SOURCES)
    sources["requirements/system.sysml"] = SYSTEM_TEXT.replace(
        "Heating element.",
        "Heating element.\n     *\n     * .. image:: _assets/a.png",
    )
    result = convert(sources, model_title="Kettle", overrides=OVERRIDES)
    assert result.asset_moves == [("requirements/_assets", "TRK-SYS/_assets")]


def test_10_main_converts_a_directory(tmp_path):
    _write(str(tmp_path), SOURCES)
    os.makedirs(tmp_path / "requirements" / "_assets")
    (tmp_path / "requirements" / "_assets" / "a.png").write_bytes(b"png")
    sources = dict(SOURCES)
    sources["requirements/system.sysml"] = SYSTEM_TEXT.replace(
        "Heating element.",
        "Heating element.\n     *\n     * .. image:: _assets/a.png",
    )
    _write(str(tmp_path), sources)
    assert tracker_convert.main([str(tmp_path), "--title", "Kettle"]) == 0
    assert (tmp_path / "MODEL.sysml").is_file()
    assert (tmp_path / "TRK-SYS" / "_assets" / "a.png").read_bytes() == b"png"
    assert not (tmp_path / "requirements").exists()
    assert (tmp_path / "library" / "Lib.sysml").is_file()
