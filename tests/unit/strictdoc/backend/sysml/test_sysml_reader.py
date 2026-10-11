import pytest

from strictdoc.backend.sdoc.models.node import SDocNode
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
    assert part_nodes[0].relations[0].role == "Satisfies"
    assert part_nodes[0].relations[0].ref_uid == "SYS-1"
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


def test_06_satisfy_target_not_found_is_an_error():
    text = """\
package 'D' {
    part def Pump {
        satisfy 'SYS-1' by nothing_here;
    }
}
"""
    with pytest.raises(StrictDocException) as exc_info:
        SysMLReader.read_from_string(
            text, file_path="d.sysml", relative_path="d.sysml"
        )
    assert "nothing_here" in str(exc_info.value)
