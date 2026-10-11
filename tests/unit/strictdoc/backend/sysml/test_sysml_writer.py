import pytest

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.document_grammar import DocumentGrammar
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.backend.sysml.sysml_format import SysMLFormat
from strictdoc.backend.sysml.writer import SysMLWriter
from strictdoc.core.document_meta import DocumentMeta
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.paths import SDocRelativePath

CANONICAL_TEXT = """\
package 'Halcyon dPCR-24 system requirements' {
    doc /*
     * Free text shown at the top of the document.
     */

    private import ScalarValues::*;

    package 'Throughput' {
        doc /*
         * Section text.
         */

        requirement <'SYS-THR-001'> 'Shift throughput' {
            doc /*
             * The instrument shall complete at least 96 samples
             * in an 8-hour shift.
             */
            attribute requiredSamplesPerShift : Real = 96;
            attribute measuredSamplesPerShift : Real;
            require constraint {
                measuredSamplesPerShift >= requiredSamplesPerShift
            }
        }

        #derivation dependency from 'SYS-THR-001' to 'STK-THR-001';
    }
}
"""


def _roundtrip(text: str) -> str:
    document = SysMLReader.read_from_string(
        text, file_path="t.sysml", relative_path="t.sysml"
    )
    return SysMLWriter.write(document)


def test_01_canonical_file_round_trips_byte_for_byte():
    assert _roundtrip(CANONICAL_TEXT) == CANONICAL_TEXT


def test_02_round_trip_is_idempotent_for_non_canonical_input():
    non_canonical = CANONICAL_TEXT.replace("    ", "  ")
    first = _roundtrip(non_canonical)
    assert _roundtrip(first) == first


def test_03_plain_dependency_form_is_kept_without_derivation_prefix():
    text = CANONICAL_TEXT.replace("#derivation ", "")
    output = _roundtrip(text)
    assert "        dependency from 'SYS-THR-001' to 'STK-THR-001';" in output
    assert "#derivation" not in output
    assert output == text


def test_04_empty_document_is_written_as_empty_package():
    text = "package 'Empty' {\n}\n"
    assert _roundtrip(text) == text


def test_05_quotes_and_backslashes_in_names_are_escaped():
    text = (
        "package 'Bob\\'s package' {\n"
        "    requirement <'R-1'> 'Say \\'hi\\' \\\\ now' {\n"
        "    }\n"
        "}\n"
    )
    document = SysMLReader.read_from_string(
        text, file_path="t.sysml", relative_path="t.sysml"
    )
    assert document.title == "Bob's package"
    requirement_ = document.section_contents[0]
    assert requirement_.reserved_title == "Say 'hi' \\ now"
    assert _roundtrip(text) == text


def test_06_attributes_with_and_without_values_and_units():
    text = """\
package 'P' {
    requirement <'R-1'> 'Title' {
        attribute bare : Real;
        attribute valued : Real = 40 [s];
        attribute untyped = 3;
    }
}
"""
    assert _roundtrip(text) == text


def test_07_design_document_is_refused():
    text = "package 'D' {\n    part def Pump;\n}\n"
    document = SysMLReader.read_from_string(
        text, file_path="d.sysml", relative_path="d.sysml"
    )
    with pytest.raises(StrictDocException) as exc_info:
        SysMLWriter.write(document)
    assert "read only" in str(exc_info.value)


def test_08_line_notes_and_block_comments_are_not_preserved():
    text = """\
package 'P' {
    // a note
    comment /* dropped */
    requirement <'R-1'> 'T' {
    }
}
"""
    expected = "package 'P' {\n    requirement <'R-1'> 'T' {\n    }\n}\n"
    assert _roundtrip(text) == expected


def test_09_new_empty_document_from_default_grammar_is_a_requirements_package(
    tmp_path,
):
    # The web UI creates a new document with the default SDoc grammar and no
    # nodes. The SysML format must write it as a valid package.
    path_to_file = tmp_path / "new_document.sysml"
    document = SDocDocument(
        mid=None,
        title="New document",
        config=None,
        view=None,
        grammar=DocumentGrammar.create_default(parent=None),
        section_contents=[],
    )
    document.meta = DocumentMeta(
        level=0,
        file_tree_mount_folder="NOT_RELEVANT",
        document_filename="new_document.sysml",
        document_filename_base="new_document",
        input_doc_full_path=str(path_to_file),
        input_doc_rel_path=SDocRelativePath("new_document.sysml"),
        input_doc_dir_rel_path=SDocRelativePath(""),
        input_doc_assets_dir_rel_path=SDocRelativePath("_assets"),
        output_document_dir_full_path="NOT_RELEVANT",
        output_document_dir_rel_path=SDocRelativePath("FIXME"),
    )
    SysMLFormat().write_document_to_file(document, project_config=None)
    assert path_to_file.read_text(encoding="utf8") == (
        "package 'New document' {\n}\n"
    )
