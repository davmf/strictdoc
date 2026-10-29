from typing import Dict, Optional

import pytest

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sdoc.models.reference import ParentReqReference
from strictdoc.backend.sysml import editor, node_data, version_tracking
from strictdoc.backend.sysml.editor import SysMLEditError
from strictdoc.backend.sysml.model import (
    SysMLDependency,
    SysMLElement,
    SysMLMetadataUsage,
    SysMLSatisfy,
    SysMLVerify,
)
from strictdoc.backend.sysml.parser import SysMLParser
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.backend.sysml.versioning import (
    LIBRARY_FILE_NAME,
    LIBRARY_TEXT,
    content_hash,
    ensure_library,
)
from strictdoc.backend.sysml.writer import SysMLWriter
from strictdoc.helpers.exception import StrictDocException

REQUIREMENTS_TEXT = """\
package 'Requirements' {
    requirement <'STK-1'> 'Parent' {
        @StrictDocVersioning::ItemVersion { version = 2; contentHash = "0000"; }
        doc /*
         * The parent text.
         */
    }

    requirement <'SYS-1'> 'Child' {
        doc /*
         * The child text.
         */
    }

    dependency from 'SYS-1' to 'STK-1' {
        @StrictDocVersioning::TracedVersion { version = 1; }
    }
}
"""

DESIGN_TEXT = """\
package 'Design' {
    part def Pump {
        @StrictDocVersioning::ItemVersion { version = 1; contentHash = "HASH"; }
        doc /*
         * The pump moves sample into the chip.
         */
        attribute flowRate : Real = 2;
        satisfy 'SYS-1' by pump;
        part pump : Pump;
    }

    part def Valve;
}
"""


def _read(text: str, item_versioning: bool = True) -> SDocDocument:
    return SysMLReader.read_from_string(
        text,
        file_path=None,
        relative_path="file.sysml",
        item_versioning=item_versioning,
    )


def _node(document: SDocDocument, uid: str) -> SDocNode:
    for node_ in version_tracking.iterate_nodes(document):
        if node_.reserved_uid == uid:
            return node_
    raise AssertionError(uid)


def _satisfy_relation(node: SDocNode) -> ParentReqReference:
    """The Satisfies relation of a usage, which also has a Typed by relation."""
    return next(
        relation_
        for relation_ in node.relations
        if isinstance(relation_, ParentReqReference)
        and relation_.role == "Satisfies"
    )


def _with_correct_hash(text: str, uid: str) -> str:
    """Replace the HASH placeholder with the hash that the reader computes."""
    document = _read(text)
    computed = node_data.get_computed_hash(_node(document, uid))
    assert computed is not None
    return text.replace('"HASH"', f'"{computed}"')


def _lookup(versions: Dict[str, int]):
    def lookup(uid: str) -> Optional[int]:
        return versions.get(uid)

    return lookup


def test_01_parser_reads_bodies_of_traces_and_metadata_values():
    model = SysMLParser.parse_string(
        """\
package 'P' {
    dependency from 'A' to 'B' {
        @StrictDocVersioning::TracedVersion { version = 4; }
    }
    part def X {
        satisfy 'A' by x { @StrictDocVersioning::TracedVersion { version = 2; } }
        verify 'B' { @TracedVersion { version = 3; } }
    }
}
"""
    )
    package_members = model.members[0].members
    dependency = package_members[0]
    assert isinstance(dependency, SysMLDependency)
    assert dependency.body_span is not None
    usage = dependency.members[0]
    assert isinstance(usage, SysMLMetadataUsage)
    assert usage.name == "StrictDocVersioning::TracedVersion"
    assert usage.values == {"version": "4"}

    element = package_members[1]
    assert isinstance(element, SysMLElement)
    satisfy, verify = element.members
    assert isinstance(satisfy, SysMLSatisfy)
    assert isinstance(verify, SysMLVerify)
    assert isinstance(satisfy.members[0], SysMLMetadataUsage)
    assert isinstance(verify.members[0], SysMLMetadataUsage)
    assert verify.members[0].name == "TracedVersion"


def test_02_versioned_requirements_package_stays_a_requirements_package():
    document = _read(REQUIREMENTS_TEXT, item_versioning=False)
    assert not document.autogen

    parent = _node(document, "STK-1")
    item_version = node_data.get_item_version(parent)
    assert item_version is not None
    assert item_version.version == 2
    assert item_version.content_hash == "0000"
    assert parent.get_field_by_name("ITEM_VERSION").get_text_value() == "2"

    child = _node(document, "SYS-1")
    assert node_data.get_item_version(child) is None
    relation = child.relations[0]
    assert isinstance(relation, ParentReqReference)
    assert node_data.get_traced_version(relation) == 1


def test_03_versioned_requirements_package_round_trips_byte_for_byte():
    document = _read(REQUIREMENTS_TEXT)
    assert SysMLWriter.write(document) == REQUIREMENTS_TEXT


def test_04_requirement_hash_ignores_layout_and_item_version():
    compact = REQUIREMENTS_TEXT.replace(
        "        doc /*\n         * The parent text.\n         */\n",
        "        doc /* The parent text. */\n",
    )
    document = _read(REQUIREMENTS_TEXT)
    compact_document = _read(compact)
    assert node_data.get_computed_hash(
        _node(document, "STK-1")
    ) == node_data.get_computed_hash(_node(compact_document, "STK-1"))


def test_05_save_gives_versions_to_unversioned_requirements_and_pins():
    text = REQUIREMENTS_TEXT.replace(
        """ {
        @StrictDocVersioning::TracedVersion { version = 1; }
    }""",
        ";",
    )
    document = _read(text)
    parent = _node(document, "STK-1")
    child = _node(document, "SYS-1")
    parent_hash = node_data.get_computed_hash(parent)

    version_tracking.update_requirement_versions(
        document, version_tracking.index_target_version_lookup(None, document)
    )

    # STK-1 has a stored hash that does not match, so it is bumped.
    assert node_data.get_item_version(parent).version == 3
    assert node_data.get_item_version(parent).content_hash == parent_hash
    assert parent.get_field_by_name("ITEM_VERSION").get_text_value() == "3"
    assert node_data.get_item_version(child).version == 1
    # The new dependency is pinned to the version after the bump.
    assert node_data.get_traced_version(child.relations[0]) == 3


def test_06_save_bumps_only_changed_requirements():
    document = _read(REQUIREMENTS_TEXT)
    lookup = version_tracking.index_target_version_lookup(None, document)
    version_tracking.update_requirement_versions(document, lookup)
    parent = _node(document, "STK-1")
    child = _node(document, "SYS-1")
    assert node_data.get_item_version(parent).version == 3
    assert node_data.get_item_version(child).version == 1

    child.set_field_value(
        field_name="STATEMENT", form_field_index=0, value="New child text.\n"
    )
    version_tracking.update_requirement_versions(document, lookup)
    assert node_data.get_item_version(parent).version == 3
    assert node_data.get_item_version(child).version == 2
    # An existing pin is not moved by a save.
    assert node_data.get_traced_version(child.relations[0]) == 1


def test_07_save_keeps_a_version_that_the_user_entered():
    document = _read(REQUIREMENTS_TEXT)
    parent = _node(document, "STK-1")
    parent.set_field_value(
        field_name="ITEM_VERSION", form_field_index=0, value="7"
    )
    version_tracking.update_requirement_versions(
        document, version_tracking.index_target_version_lookup(None, document)
    )
    assert node_data.get_item_version(parent).version == 7


def test_08_suspect_traces_and_review():
    document = _read(REQUIREMENTS_TEXT)
    child = _node(document, "SYS-1")
    lookup = version_tracking.index_target_version_lookup(None, document)

    suspects = version_tracking.suspect_traces(child, lookup)
    assert len(suspects) == 1
    assert suspects[0].traced_version == 1
    assert suspects[0].current_version == 2

    changed = version_tracking.review_traces(child, lookup)
    assert len(changed) == 1
    assert node_data.get_traced_version(child.relations[0]) == 2
    assert version_tracking.suspect_traces(child, lookup) == []


def test_09_invalid_version_is_reported_with_location():
    text = REQUIREMENTS_TEXT.replace("version = 2;", "version = two;")
    with pytest.raises(StrictDocException, match="line 2.*whole number"):
        _read(text)


def test_10_content_hash_ignores_whitespace_and_empty_bodies():
    assert content_hash("part p { }") == content_hash("part p;")
    assert content_hash("part  p\n    : T;") == content_hash("part p : T;")
    assert content_hash("part p;") != content_hash("part q;")


def test_11_design_element_hash_matches_when_stored_correctly():
    text = _with_correct_hash(DESIGN_TEXT, "Design::Pump")
    pump = _node(_read(text), "Design::Pump")
    item_version = node_data.get_item_version(pump)
    assert item_version is not None
    assert item_version.content_hash == node_data.get_computed_hash(pump)
    assert pump.get_field_by_name("ITEM_VERSION").get_text_value() == "1"
    # `satisfy ... by pump` gives the relation to the usage, not the def.
    pump_usage = _node(_read(text), "Design::Pump::pump")
    assert node_data.get_statement_offset(_satisfy_relation(pump_usage)) is not None


def test_12_apply_versioning_bumps_changed_element_and_its_parent():
    old_text = _with_correct_hash(DESIGN_TEXT, "Design::Pump")
    new_text = old_text.replace("part pump : Pump;", "part pump : Pump [2];")

    result = editor.apply_versioning(old_text, new_text, _lookup({}))

    document = _read(result)
    pump_def = _node(document, "Design::Pump")
    assert node_data.get_item_version(pump_def).version == 2
    # The nested usage changed, so it gets its first version.
    pump_usage = _node(document, "Design::Pump::pump")
    assert node_data.get_item_version(pump_usage).version == 1
    # Each stored hash matches the hash computed from the written text.
    for node_ in (pump_def, pump_usage):
        assert node_data.get_item_version(
            node_
        ).content_hash == node_data.get_computed_hash(node_)
    # The unchanged element is not versioned.
    assert node_data.get_item_version(_node(document, "Design::Valve")) is None
    assert "    part def Valve;\n" in result
    assert "part pump : Pump [2] {\n" in result


def test_13_apply_versioning_keeps_unchanged_file_and_manual_version():
    old_text = _with_correct_hash(DESIGN_TEXT, "Design::Pump")
    assert editor.apply_versioning(old_text, old_text, _lookup({})) == (
        old_text
    )

    new_text = old_text.replace("version = 1;", "version = 5;").replace(
        "flowRate : Real = 2", "flowRate : Real = 3"
    )
    result = editor.apply_versioning(old_text, new_text, _lookup({}))
    pump = _node(_read(result), "Design::Pump")
    assert node_data.get_item_version(pump).version == 5
    assert node_data.get_item_version(
        pump
    ).content_hash == node_data.get_computed_hash(pump)


def test_14_apply_versioning_pins_new_traces_only():
    old_text = _with_correct_hash(DESIGN_TEXT, "Design::Pump")
    new_text = old_text.replace(
        "    part def Valve;\n",
        "    part def Valve {\n        satisfy 'SYS-2' by valve;\n"
        "        part valve : Valve;\n    }\n",
    )

    result = editor.apply_versioning(
        old_text, new_text, _lookup({"SYS-1": 4, "SYS-2": 9})
    )

    assert "satisfy 'SYS-1' by pump;" in result
    assert (
        "satisfy 'SYS-2' by valve {\n"
        "            @StrictDocVersioning::TracedVersion { version = 9; }\n"
        "        }"
    ) in result
    valve_usage = _node(_read(result), "Design::Valve::valve")
    assert node_data.get_traced_version(_satisfy_relation(valve_usage)) == 9


def test_15_review_traces_sets_and_replaces_pins():
    text = DESIGN_TEXT.replace(
        "satisfy 'SYS-1' by pump;",
        "satisfy 'SYS-1' by pump {\n"
        "            @StrictDocVersioning::TracedVersion { version = 1; }\n"
        "        }",
    )
    document = _read(text)
    relation = _satisfy_relation(_node(document, "Design::Pump::pump"))
    offset = node_data.get_statement_offset(relation)
    assert offset is not None

    result = editor.review_traces(text, {offset: 3})

    assert "TracedVersion { version = 3; }" in result
    assert "TracedVersion { version = 1; }" not in result
    with pytest.raises(SysMLEditError):
        editor.review_traces(text, {offset + 1: 3})


def test_16_ensure_library_writes_the_library_once(tmp_path):
    path = ensure_library(str(tmp_path))
    assert path == str(tmp_path / LIBRARY_FILE_NAME)
    assert (tmp_path / LIBRARY_FILE_NAME).read_text() == LIBRARY_TEXT
    assert ensure_library(str(tmp_path)) is None
    library = _read(LIBRARY_TEXT)
    assert library.autogen
    assert library.title == "StrictDocVersioning"
