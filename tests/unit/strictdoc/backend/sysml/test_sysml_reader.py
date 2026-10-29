import pytest

from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sysml import node_data
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.helpers.exception import StrictDocException

REQUIREMENTS_TEXT = """\
package 'System' {
    doc /*
     * Document text.
     */

    private import ScalarValues::*;

    package 'Throughput' {
        doc /*
         * Section text.
         */

        requirement <'SYS-1'> 'Shift throughput' {
            doc /*
             * Statement line.
             */
            attribute required : Real = 96;
            attribute measured : Real;
            require constraint {
                measured >= required
            }
        }

        #derivation dependency from 'SYS-1' to 'STK-1';
    }
}
"""

DESIGN_TEXT = """\
package 'Design' {
    part def Pump {
        doc /* A pump. */
        satisfy 'SYS-1' by pump;
        part pump : Pump;
    }
    verification def Check {
        objective {
            verify 'SYS-1';
        }
    }
}
"""


def _nodes_of_type(container, node_type):
    result = []
    for child_ in container.section_contents:
        if isinstance(child_, SDocNode) and child_.node_type == node_type:
            result.append(child_)
        if hasattr(child_, "section_contents"):
            result.extend(_nodes_of_type(child_, node_type))
    return result


def test_01_requirements_package_is_editable_and_maps_to_nodes():
    document = SysMLReader.read_from_string(
        REQUIREMENTS_TEXT,
        file_path="system.sysml",
        relative_path="system.sysml",
    )
    assert document.title == "System"
    assert document.autogen is False
    assert document.grammar.elements_by_type["REQUIREMENT"] is not None
    sections = _nodes_of_type(document, "SECTION")
    assert [section_.reserved_title for section_ in sections] == ["Throughput"]
    requirements = _nodes_of_type(document, "REQUIREMENT")
    assert len(requirements) == 1
    requirement_ = requirements[0]
    assert requirement_.reserved_uid == "SYS-1"
    assert requirement_.reserved_title == "Shift throughput"
    assert requirement_.reserved_statement == "Statement line."
    assert requirement_.get_field_by_name("REQUIRED").get_text_value() == "96"
    assert (
        requirement_.get_field_by_name("CONSTRAINT").get_text_value()
        == "measured >= required"
    )
    assert [relation_.ref_uid for relation_ in requirement_.relations] == [
        "STK-1"
    ]


def test_02_requirement_mid_is_stable_across_reads():
    first = SysMLReader.read_from_string(
        REQUIREMENTS_TEXT, file_path="a.sysml", relative_path="a.sysml"
    )
    second = SysMLReader.read_from_string(
        REQUIREMENTS_TEXT, file_path="a.sysml", relative_path="a.sysml"
    )
    first_requirement = _nodes_of_type(first, "REQUIREMENT")[0]
    second_requirement = _nodes_of_type(second, "REQUIREMENT")[0]
    assert first_requirement.reserved_mid == second_requirement.reserved_mid


def test_03_design_package_is_read_only_with_satisfy_and_verify_relations():
    document = SysMLReader.read_from_string(
        DESIGN_TEXT, file_path="design.sysml", relative_path="design.sysml"
    )
    assert document.autogen is True
    pump_nodes = _nodes_of_type(document, "PART_DEF")
    assert len(pump_nodes) == 1
    pump_ = pump_nodes[0]
    assert pump_.autogen is True
    assert pump_.reserved_uid == "Design::Pump"
    assert pump_.get_field_by_name("ELEMENT_KIND").get_text_value() == (
        "part def"
    )
    assert [
        (relation_.role, relation_.ref_uid) for relation_ in pump_.relations
    ] == []
    part_nodes = _nodes_of_type(pump_, "PART")
    # `part pump : Pump` also gives a candidate relation, see test_17.
    assert [
        (relation_.role, relation_.ref_uid)
        for relation_ in part_nodes[0].relations
    ] == [("Typed by", "Pump"), ("Satisfies", "SYS-1")]
    check_ = _nodes_of_type(document, "VERIFICATION_DEF")[0]
    assert check_.relations[0].role == "Verifies"
    assert check_.relations[0].ref_uid == "SYS-1"


def test_04_requirement_with_unrepresentable_content_makes_design_package():
    text = """\
package 'P' {
    requirement <'R-1'> 'Title' {
        attribute x : Real = 1 [s];
        attribute x : Real = 2;
    }
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="p.sysml", relative_path="p.sysml"
    )
    assert document.autogen is True


def test_05_dependency_from_unknown_requirement_is_an_error():
    text = """\
package 'P' {
    dependency from 'MISSING' to 'OTHER';
}
"""
    with pytest.raises(StrictDocException) as exc_info:
        SysMLReader.read_from_string(
            text, file_path="p.sysml", relative_path="p.sysml"
        )
    assert "p.sysml, line 2" in str(exc_info.value)


def test_06_satisfy_target_not_in_file_becomes_a_placeholder_node():
    text = """\
package 'D' {
    part def Pump {
        satisfy 'SYS-1' by nothing_here;
    }
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="d.sysml", relative_path="d.sysml"
    )
    placeholders = _nodes_of_type(document, "SATISFY")
    assert len(placeholders) == 1
    assert (
        placeholders[0].get_field_by_name("SATISFIED_BY_PATH").get_text_value()
        == "nothing_here"
    )
    assert placeholders[0].relations[0].role == "Satisfies"


def test_06b_satisfy_outside_element_without_by_is_an_error():
    text = """\
package 'D' {
    satisfy 'SYS-1';
}
"""
    with pytest.raises(StrictDocException) as exc_info:
        SysMLReader.read_from_string(
            text, file_path="d.sysml", relative_path="d.sysml"
        )
    assert "d.sysml, line 2" in str(exc_info.value)


def test_07_anonymous_redefinitions_get_owner_qualified_unique_uids():
    text = """\
package 'D' {
    part def Scenario {
        part :>> stations;
        part :>> stations;
        part :>> configuration : Config;
    }
    part def Other {
        part :>> stations;
    }
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="d.sysml", relative_path="d.sysml"
    )
    uids = [node_.reserved_uid for node_ in _nodes_of_type(document, "PART")]
    assert uids == [
        "D::Scenario::stations",
        "D::Scenario::stations_2",
        "D::Scenario::configuration",
        "D::Other::stations",
    ]


def test_08_duplicate_names_are_suffixed_not_fatal():
    text = """\
package 'D' {
    part def Pump;
    part def Pump;
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="d.sysml", relative_path="d.sysml"
    )
    uids = [
        node_.reserved_uid for node_ in _nodes_of_type(document, "PART_DEF")
    ]
    assert uids == ["D::Pump", "D::Pump_2"]


def test_09_satisfy_attaches_to_deepest_node_on_dot_path():
    text = """\
package 'D' {
    part baseSteady {
        part configuration {
            part cartridge;
        }
    }
    satisfy 'SYS-1' by baseSteady.configuration.cartridge;
    satisfy 'SYS-2' by baseSteady.configuration.missing;
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="d.sysml", relative_path="d.sysml"
    )
    cartridge_ = _nodes_of_type(document, "PART")[2]
    assert cartridge_.reserved_uid == "D::baseSteady::configuration::cartridge"
    satisfied_ = [
        (relation_.role, relation_.ref_uid)
        for relation_ in cartridge_.relations
    ]
    assert satisfied_ == [("Satisfies", "SYS-1")]
    assert (
        cartridge_.get_field_by_name("SATISFIED_BY_PATH").get_text_value()
        == "SYS-1: baseSteady.configuration.cartridge"
    )
    # SYS-2 names baseSteady.configuration.missing. The deepest existing node
    # is configuration, so the relation attaches there, and no placeholder is
    # created.
    configuration_ = _nodes_of_type(document, "PART")[1]
    assert [
        (relation_.role, relation_.ref_uid)
        for relation_ in configuration_.relations
    ] == [("Satisfies", "SYS-2")]
    assert (
        configuration_.get_field_by_name("SATISFIED_BY_PATH").get_text_value()
        == "SYS-2: baseSteady.configuration.missing"
    )
    assert _nodes_of_type(document, "SATISFY") == []


def test_10_design_package_keeps_image_directive_and_wraps_source():
    text = """\
package 'Design' {
    part def Pump {
        doc /*
         * Pump layout:
         *
         * .. image:: ./_assets/pump.png
         */
        part pump : Pump;
    }
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="design.sysml", relative_path="design.sysml"
    )
    assert document.config.get_markup() == "RST"
    pump_ = _nodes_of_type(document, "PART_DEF")[0]
    statement = pump_.get_field_by_name("STATEMENT").get_text_value()
    assert ".. image:: ./_assets/pump.png" in statement
    source = pump_.get_field_by_name("SOURCE").get_text_value()
    assert "<details>" in source
    assert "\n.. code-block:: text\n\n    part def Pump {" in source


def test_11_design_node_lists_members_in_a_table():
    text = """\
package 'Design' {
    action def SampleProcedure;
    part sample {
        perform action sampleProcedure : SampleProcedure {
            in part :>> cart = cartridge;
            attribute volume : Real = 5 [mL];
        }
    }
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="design.sysml", relative_path="design.sysml"
    )
    procedure_ = _nodes_of_type(document, "ACTION")[0]
    members = procedure_.get_field_by_name("MEMBERS").get_text_value()
    assert members.startswith("**parts**\n\n.. list-table::")
    assert "\n\n**attributes**\n\n.. list-table::" in members
    assert "Redefines" in members
    assert "``cartridge``" in members
    assert "Kind" not in members
    assert "``Real``" in members
    assert ":>>" not in members
    sample_ = _nodes_of_type(document, "PART")[0]
    assert "MEMBERS" in sample_.ordered_fields_lookup
    leaf_ = _nodes_of_type(document, "ACTION_DEF")[0]
    assert "MEMBERS" not in leaf_.ordered_fields_lookup


def test_12_design_node_lists_properties_in_a_table():
    text = """\
package 'Design' {
    part def Pump;
    part pump : Pump [2];
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="design.sysml", relative_path="design.sysml"
    )
    pump_ = _nodes_of_type(document, "PART")[0]
    details = pump_.get_field_by_name("DETAILS").get_text_value()
    assert details.splitlines()[:2] == ["**parts**", ""]
    assert details.splitlines()[2] == ".. list-table::"
    assert details.splitlines()[5:] == [
        "    * - Name",
        "      - Type",
        "      - Multiplicity",
        "    * - ``pump``",
        "      - ``Pump``",
        "      - ``[2]``",
    ]
    assert "``Pump``" in details
    assert "Modifiers" not in details


def test_13_design_node_shows_units_in_a_separate_column():
    text = """\
package 'Design' {
    part rig {
        attribute pitch = 0.05 [mm];
        attribute rate = 120 [Hz];
        attribute count = 3;
        attribute item = list[0];
    }
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="design.sysml", relative_path="design.sysml"
    )
    members = (
        _nodes_of_type(document, "PART")[0]
        .get_field_by_name("MEMBERS")
        .get_text_value()
    )
    assert members.splitlines()[:2] == ["**attributes**", ""]
    assert members.splitlines()[5:] == [
        "    * - Name",
        "      - Value",
        "      - Units",
        "    * - ``pitch``",
        "      - ``0.05``",
        "      - ``mm``",
        "    * - ``rate``",
        "      - ``120``",
        "      - ``Hz``",
        "    * - ``count``",
        "      - ``3``",
        "      - \\-",
        "    * - ``item``",
        "      - ``list[0]``",
        "      - \\-",
    ]


def test_14_design_node_groups_members_by_kind():
    text = """\
package 'Design' {
    part def Instrument {
        part rack : SampleRack;
        attribute count = 3;
        part shuttle : Shuttle;
        action def Run;
    }
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="design.sysml", relative_path="design.sysml"
    )
    instrument_ = _nodes_of_type(document, "PART_DEF")[0]
    details = instrument_.get_field_by_name("DETAILS").get_text_value()
    assert details.startswith("**part-defs**\n\n.. list-table::")
    assert "Kind" not in details
    members = instrument_.get_field_by_name("MEMBERS").get_text_value()
    headings = [
        line_ for line_ in members.splitlines() if line_.startswith("**")
    ]
    assert headings == ["**parts**", "**attributes**", "**action-defs**"]
    parts_table = members.split("**attributes**")[0]
    assert "``rack``" in parts_table
    assert "``shuttle``" in parts_table
    assert "``count``" not in parts_table


def test_15_design_node_keeps_name_column_for_anonymous_members():
    text = """\
package 'Design' {
    verification def PumpTest {
        objective {
            doc /* The pump delivers the flow. */
        }
    }
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="design.sysml", relative_path="design.sysml"
    )
    test_ = _nodes_of_type(document, "VERIFICATION_DEF")[0]
    members = test_.get_field_by_name("MEMBERS").get_text_value()
    assert members.splitlines() == [
        "**objectives**",
        "",
        ".. list-table::",
        "    :header-rows: 1",
        "",
        "    * - Name",
        "    * - \\-",
    ]


def test_16_design_node_records_type_lineage_within_the_file():
    text = """\
package 'Scenarios' {
    part def Scenario;
    part def BaseSteadyStat :> Scenario;
    part def Instrument;
    part baseSteady : BaseSteadyStat;
    part instrument : Instrument;
    part external : Library::Other;
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="design.sysml", relative_path="design.sysml"
    )
    lineages = {
        node_.reserved_title: node_data.get_type_lineage(node_)
        for node_ in _nodes_of_type(document, "PART")
        + _nodes_of_type(document, "PART_DEF")
    }
    assert lineages == {
        "Scenario": [],
        "BaseSteadyStat": ["Scenario"],
        "Instrument": [],
        "baseSteady": ["BaseSteadyStat", "Scenario"],
        "instrument": ["Instrument"],
        "external": ["Other"],
    }


def test_17_type_references_become_candidate_relations():
    text = """\
package 'Runs' {
    private import ScalarValues::*;
    part def Rig :> Bench;
    verification <'TR-1'> 'Run of check' :> Cases::'TC-1' {
        subject dut : 'CONF-1', 'REL-1';
        attribute build : String = "v1";
        attribute result : Result;
        verification 'Step' :>> 'TC-1'::step;
    }
}
"""
    document = SysMLReader.read_from_string(
        text, file_path="runs.sysml", relative_path="runs.sysml"
    )
    run_ = _nodes_of_type(document, "VERIFICATION")[0]
    assert [
        (
            relation_.role,
            relation_.ref_uid,
            node_data.get_candidate_uids(relation_),
        )
        for relation_ in run_.relations
    ] == [
        ("Subsets", "Cases::TC-1", ["Cases::TC-1", "TC-1"]),
        ("References", "CONF-1", ["CONF-1"]),
        ("References", "REL-1", ["REL-1"]),
        ("References", "String", ["String"]),
        ("References", "Result", ["Result"]),
    ]
    step_ = _nodes_of_type(run_, "VERIFICATION")[0]
    assert [
        (relation_.role, relation_.ref_uid) for relation_ in step_.relations
    ] == [("Redefines", "TC-1::step")]
    rig_ = _nodes_of_type(document, "PART_DEF")[0]
    assert [
        (relation_.role, relation_.ref_uid) for relation_ in rig_.relations
    ] == [("Specializes", "Bench")]


def test_18_satisfy_and_verify_relations_have_no_candidates():
    document = SysMLReader.read_from_string(
        DESIGN_TEXT, file_path="design.sysml", relative_path="design.sysml"
    )
    check_ = _nodes_of_type(document, "VERIFICATION_DEF")[0]
    assert node_data.get_candidate_uids(check_.relations[0]) is None
