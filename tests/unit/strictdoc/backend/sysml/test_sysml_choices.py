from types import SimpleNamespace

from strictdoc.backend.sdoc.models.grammar_element import (
    GrammarElementFieldSingleChoice,
    GrammarElementFieldString,
)
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sysml import choices, node_data
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.backend.sysml.writer import SysMLWriter

REQUIREMENTS_TEXT = """\
package 'Requirements' {
    private import Choices::Tracker::*;

    requirement <'REQ-1'> 'First' {
        doc /*
         * First statement.
         */
        attribute status : Status = Status::'Waiting for approval';
        attribute referenceId : String = "2.4";
    }

    requirement <'REQ-2'> 'Second' {
        doc /*
         * Second statement.
         */
        attribute status : Status = Status::Draft;
    }
}
"""

LIBRARY_TEXT = """\
package Choices {
    package Tracker {
        enum def Status {
            enum Draft;
            enum 'Waiting for approval';
            enum Approved;
        }
    }
}
"""


def _read(text: str, path: str = "requirements.sysml"):
    return SysMLReader.read_from_string(
        text, file_path=path, relative_path=path
    )


def _requirements(document):
    return [
        node_
        for node_ in document.section_contents
        if isinstance(node_, SDocNode) and node_.node_type == "REQUIREMENT"
    ]


def _field(node: SDocNode, field_title: str) -> str:
    return node.ordered_fields_lookup[field_title][0].get_text_value()


def _index(*documents):
    return SimpleNamespace(
        document_tree=SimpleNamespace(document_list=list(documents))
    )


def test_01_enum_literal_is_read_as_its_bare_name():
    document = _read(REQUIREMENTS_TEXT)
    first, second = _requirements(document)
    assert _field(first, "STATUS") == "Waiting for approval"
    assert _field(second, "STATUS") == "Draft"
    # A String attribute keeps its value text.
    assert _field(first, "REFERENCE_ID") == '"2.4"'
    assert node_data.get_choice_types(document) == {"STATUS": "Status"}


def test_02_enum_typed_attributes_round_trip_byte_for_byte():
    assert SysMLWriter.write(_read(REQUIREMENTS_TEXT)) == REQUIREMENTS_TEXT


def test_03_changed_literal_is_written_qualified_and_quoted():
    document = _read(REQUIREMENTS_TEXT)
    first, second = _requirements(document)
    first.set_field_value(
        field_name="STATUS", form_field_index=0, value="Approved"
    )
    second.set_field_value(
        field_name="STATUS", form_field_index=0, value="Needs work"
    )
    text = SysMLWriter.write(document)
    assert "attribute status : Status = Status::Approved;" in text
    assert "attribute status : Status = Status::'Needs work';" in text


def test_04_new_attribute_of_a_choice_field_gets_the_enum_type():
    document = _read(REQUIREMENTS_TEXT)
    second = _requirements(document)[1]
    node_data.set_attribute_types(second, {})
    text = SysMLWriter.write(document)
    assert text.count("attribute status : Status = Status::Draft;") == 1


def test_05_enum_definitions_are_collected_by_qualified_name():
    library = _read(LIBRARY_TEXT, path="Choices.sysml")
    assert node_data.get_enum_definitions(library) == {
        ("Choices", "Tracker", "Status"): [
            "Draft",
            "Waiting for approval",
            "Approved",
        ]
    }


def test_06_types_resolve_by_qualified_name_and_wildcard_import():
    definitions = {("Choices", "Tracker", "Status"): ["Draft"]}
    namespaces = [("Choices", "Tracker")]
    assert choices.resolve_enum("Status", namespaces, definitions) == ["Draft"]
    assert choices.resolve_enum(
        "Choices::'Tracker'::Status", [], definitions
    ) == ["Draft"]
    assert choices.resolve_enum("Status", [], definitions) is None


def test_07_choice_field_becomes_single_choice_with_enum_literals():
    document = _read(REQUIREMENTS_TEXT)
    library = _read(LIBRARY_TEXT, path="Choices.sysml")
    choices.apply_choice_fields(_index(document, library))

    element = document.grammar.elements_by_type["REQUIREMENT"]
    status_field = element.fields_map["STATUS"]
    assert isinstance(status_field, GrammarElementFieldSingleChoice)
    assert status_field.options == ["Draft", "Waiting for approval", "Approved"]
    assert status_field in element.fields
    assert document.get_options_for_field("REQUIREMENT", "STATUS") == [
        "Draft",
        "Waiting for approval",
        "Approved",
    ]
    assert isinstance(
        element.fields_map["REFERENCE_ID"], GrammarElementFieldString
    )


def test_08_choice_field_stays_a_string_without_its_enum_definition():
    document = _read(REQUIREMENTS_TEXT)
    choices.apply_choice_fields(_index(document))
    element = document.grammar.elements_by_type["REQUIREMENT"]
    assert isinstance(element.fields_map["STATUS"], GrammarElementFieldString)
