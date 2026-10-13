import pytest

from strictdoc.backend.sysml.model import (
    SysMLAllocate,
    SysMLAttribute,
    SysMLBehaviourControl,
    SysMLBlockComment,
    SysMLDependency,
    SysMLDocComment,
    SysMLElement,
    SysMLElseThen,
    SysMLIfThen,
    SysMLImport,
    SysMLLineNote,
    SysMLMetadataUsage,
    SysMLOpaque,
    SysMLPackage,
    SysMLPerform,
    SysMLRequireConstraint,
    SysMLSatisfy,
    SysMLSuccession,
    SysMLThen,
    SysMLVerify,
)
from strictdoc.backend.sysml.parser import SysMLParseError, SysMLParser


def _parse(text: str):
    return SysMLParser.parse_string(text, file_path="test.sysml")


def test_01_package_with_name_and_short_name():
    model = _parse("package <'P1'> 'My package' { }")
    package_ = model.members[0]
    assert isinstance(package_, SysMLPackage)
    assert package_.short_name == "P1"
    assert package_.name == "My package"
    assert package_.members == []


def test_02_members_have_annotations_from_hash_prefix():
    model = _parse("package P { #derivation dependency from A to B; }")
    dependency_ = model.members[0].members[0]
    assert isinstance(dependency_, SysMLDependency)
    assert dependency_.annotations == ["derivation"]
    assert dependency_.sources == ["A"]
    assert dependency_.targets == ["B"]


def test_03_dependency_without_from_and_with_quoted_names():
    model = _parse("package P { dependency to 'STK-1', 'STK-2'; }")
    dependency_ = model.members[0].members[0]
    assert dependency_.sources == []
    assert dependency_.targets == ["STK-1", "STK-2"]


def test_04_doc_and_block_comments_are_stripped_of_decoration():
    text = """\
package P {
    doc /*
     * First line.
     *
     *   Indented line.
     */
    comment /* a note */
}
"""
    model = _parse(text)
    package_ = model.members[0]
    doc_ = package_.members[0]
    assert isinstance(doc_, SysMLDocComment)
    assert doc_.text == "First line.\n\n  Indented line."
    comment_ = package_.members[1]
    assert isinstance(comment_, SysMLBlockComment)
    assert comment_.text == "a note"


def test_05_line_notes_are_members():
    model = _parse("// top note\npackage P { // inner note\n}\n")
    assert isinstance(model.members[0], SysMLLineNote)
    assert model.members[0].text == "// top note"
    assert isinstance(model.members[1], SysMLPackage)
    assert isinstance(model.members[1].members[0], SysMLLineNote)
    assert model.members[1].members[0].text == "// inner note"


def test_06_import_visibility_and_target():
    model = _parse("package P { private import ScalarValues::*; }")
    import_ = model.members[0].members[0]
    assert isinstance(import_, SysMLImport)
    assert import_.visibility == "private"
    assert import_.target == "ScalarValues::*"


def test_07_requirement_usage_with_attributes_and_constraint():
    text = """\
package P {
    requirement <'SYS-1'> 'Throughput' {
        doc /* The system shall work. */
        attribute required : Real = 96 [s];
        attribute measured : Real;
        require constraint {
            measured >= required
        }
    }
}
"""
    model = _parse(text)
    requirement_ = model.members[0].members[0]
    assert isinstance(requirement_, SysMLElement)
    assert requirement_.kind == "requirement"
    assert requirement_.short_name == "SYS-1"
    assert requirement_.name == "Throughput"
    assert requirement_.doc == "The system shall work."
    required_, measured_, constraint_ = requirement_.members[1:4]
    assert isinstance(required_, SysMLAttribute)
    assert required_.name == "required"
    assert required_.type_names == ["Real"]
    assert required_.value_text == "96 [s]"
    assert required_.units == "s"
    assert measured_.value_text is None
    assert isinstance(constraint_, SysMLRequireConstraint)
    assert constraint_.text == "measured >= required"
    assert requirement_.require_constraint_text == "measured >= required"


def test_08_definitions_usages_and_specialisations():
    text = """\
package P {
    part def Pump :> Base, Other {
        attribute mass : Real = 2;
    }
    variation part def Variants;
    part pump : Pump [1..*];
    item def Sample :>> size;
}
"""
    model = _parse(text)
    members = model.members[0].members
    pump_def_ = members[0]
    assert pump_def_.kind == "part"
    assert pump_def_.is_definition is True
    assert pump_def_.name == "Pump"
    assert pump_def_.specializations[0].operator == ":>"
    assert pump_def_.specializations[0].targets == ["Base", "Other"]
    assert members[1].modifiers == ["variation"]
    assert members[2].multiplicity == "[1..*]"
    assert members[2].specializations[0].targets == ["Pump"]
    assert members[3].specializations[0].operator == ":>>"


def test_09_behaviour_successions_fork_join_decide_merge_and_if_then():
    text = """\
package P {
    action step {
        first start then done;
        then next;
        fork f;
        join;
        decide;
        if x > 1 then a;
        else b;
        merge;
        perform action sub;
    }
}
"""
    model = _parse(text)
    body_ = model.members[0].members[0].members
    assert isinstance(body_[0], SysMLSuccession)
    assert (body_[0].first, body_[0].then) == ("start", "done")
    assert isinstance(body_[1], SysMLThen)
    assert isinstance(body_[2], SysMLBehaviourControl)
    assert body_[2].kind == "fork"
    assert body_[2].name == "f"
    assert isinstance(body_[5], SysMLIfThen)
    assert body_[5].condition_text == "x > 1"
    assert body_[5].condition is not None
    assert body_[5].target == "a"
    assert isinstance(body_[6], SysMLElseThen)
    assert isinstance(body_[8], SysMLPerform)


def test_10_allocate_satisfy_verify_and_objective():
    text = """\
package P {
    part def Pump {
        satisfy 'SYS-1' by pump;
        allocate step to pump;
    }
    verification def Check {
        objective {
            verify 'SYS-1';
        }
    }
}
"""
    model = _parse(text)
    members = model.members[0].members
    satisfy_ = members[0].members[0]
    assert isinstance(satisfy_, SysMLSatisfy)
    assert satisfy_.requirement == "SYS-1"
    assert satisfy_.by == "pump"
    assert isinstance(members[0].members[1], SysMLAllocate)
    objective_ = members[1].members[0]
    assert objective_.kind == "objective"
    assert isinstance(objective_.members[0], SysMLVerify)
    assert objective_.members[0].requirement == "SYS-1"


def test_11_metadata_usage_with_block():
    model = _parse("package P { @Meta { x = 1; } }")
    metadata_ = model.members[0].members[0]
    assert isinstance(metadata_, SysMLMetadataUsage)
    assert metadata_.name == "Meta"
    assert metadata_.body_text == "x = 1;"


def test_12_unknown_member_inside_body_is_opaque():
    text = """\
package P {
    some unknown construct { nested { deep } }
    connect a to b;
}
"""
    model = _parse(text)
    members = model.members[0].members
    assert all(isinstance(member_, SysMLOpaque) for member_ in members)
    assert members[0].text == "some unknown construct"
    assert "nested { deep }" in members[0].source_text
    assert members[1].text == "connect a to b"


def test_13_unknown_top_level_construct_is_a_syntax_error():
    with pytest.raises(SysMLParseError) as exc_info:
        _parse("package P { }\nsome garbage here;\n")
    message = str(exc_info.value)
    assert "test.sysml" in message
    assert "line 2" in message


def test_14_source_positions_are_line_column_and_byte_offsets():
    text = "package P {\n    part x;\n}\n"
    model = _parse(text)
    part_ = model.members[0].members[0]
    assert part_.span.line_start == 2
    assert part_.span.col_start == 5
    assert part_.span.byte_start == text.index("part x")
    assert part_.span.byte_end == text.index("part x;") + len("part x;")
    assert part_.source_text == "part x;"


def test_15_byte_offsets_count_utf8_bytes():
    text = "package P {\n    doc /* é */\n    part x;\n}\n"
    model = _parse(text)
    part_ = model.members[0].members[1]
    assert part_.span.line_start == 3
    assert part_.span.byte_start == len(text[: text.index("part x")].encode())


def test_16_attribute_value_expression_tree():
    model = _parse("package P { attribute m : Real = 2 * (3 + x) ** 2; }")
    attribute_ = model.members[0].members[0]
    assert attribute_.value_text == "2 * (3 + x) ** 2"
    assert type(attribute_.value).__name__ == "BinaryOperation"
    assert attribute_.value.operator == "*"


def test_17_calc_body_parameters_and_result_expression():
    text = """\
package P {
    calc def Flow {
        in a : Real;
        in b : Real;
        return r : Real = a * b;
        a * b + 1
    }
}
"""
    model = _parse(text)
    calc_ = model.members[0].members[0]
    assert calc_.kind == "calc"
    assert calc_.is_definition is True
    assert [member_.name for member_ in calc_.members[:2]] == ["a", "b"]
    assert calc_.members[0].modifiers == ["in"]
    assert calc_.members[2].modifiers == ["return"]
    assert calc_.result_text == "a * b + 1"
    assert type(calc_.result_expression).__name__ == "BinaryOperation"


def test_18_parse_file_reads_utf8_and_strips_bom(tmp_path):
    path = tmp_path / "file.sysml"
    path.write_bytes(b"\xef\xbb\xbfpackage 'P' { }\n")
    model = SysMLParser.parse_file(str(path))
    assert model.members[0].name == "P"
    assert model.file_path == str(path)


def test_19_prefixes_abstract_derived_readonly_end_individual():
    model = _parse(
        """\
package P {
    abstract part def <'AL-INS'> Instrument :> Configuration;
    derived attribute total : Real;
    readonly attribute fixed : Real = 1;
    end part source : Port;
    individual part sample : Item;
}
"""
    )
    members = model.members[0].members
    assert members[0].is_abstract is True
    assert members[0].short_name == "AL-INS"
    assert members[1].modifiers == ["derived"]
    assert members[2].modifiers == ["readonly"]
    assert members[3].modifiers == ["end"]
    assert members[4].modifiers == ["individual"]


def test_20_default_values_with_and_without_equals():
    model = _parse(
        """\
package P {
    attribute invalid : Boolean default false;
    attribute x : Natural default = 3;
    attribute time : DurationValue default 0 [s];
}
"""
    )
    members = model.members[0].members
    assert members[0].default_text == "false"
    assert members[0].default_value.value is False
    assert members[1].default_text == "3"
    assert members[2].default_text == "0 [s]"
    assert members[2].value_text is None


def test_21_anonymous_redefinitions_with_and_without_keyword_or_type():
    model = _parse(
        """\
package P {
    part def Config {
        :>> nominal = 10 [s];
        attribute :>> count = 24;
        part :>> stations { attribute :>> capacity = 4; }
        part :>> configuration : BaseInstrument;
    }
}
"""
    )
    members = model.members[0].members[0].members
    assert members[0].name is None
    assert members[0].redefines == ["nominal"]
    assert members[0].value_text == "10 [s]"
    assert members[1].redefines == ["count"]
    assert members[1].value_text == "24"
    assert members[2].redefines == ["stations"]
    assert members[2].has_body is True
    assert members[2].members[0].redefines == ["capacity"]
    assert members[3].redefines == ["configuration"]
    assert members[3].specializations[1].targets == ["BaseInstrument"]


def test_22_dot_feature_chains_in_references_and_expressions():
    model = _parse(
        """\
package P {
    satisfy 'SYS-1' by baseSteady.configuration.cartridge;
    allocate sample.intake.prime to stations;
    attribute :>> nominal = PrimingTime(pressure = controller.setPressure);
}
"""
    )
    satisfy_, allocate_, attribute_ = model.members[0].members
    assert satisfy_.by == "baseSteady.configuration.cartridge"
    assert satisfy_.by_path == ["baseSteady", "configuration", "cartridge"]
    assert allocate_.source_path == ["sample", "intake", "prime"]
    assert allocate_.target_path == ["stations"]
    invocation_ = attribute_.value
    assert type(invocation_).__name__ == "Invocation"
    assert invocation_.arguments[0].value.path == [
        "controller",
        "setPressure",
    ]


def test_23_guarded_successions_after_decide():
    model = _parse(
        """\
package P {
    action step {
        decide bubble1;
        first bubble1 if not Bernoulli(p = pBubble) then primed;
        first bubble2 then done;
        first invalidCheck if sample.invalid then reflexRetest;
    }
}
"""
    )
    members = model.members[0].members[0].members
    guarded_ = members[1]
    assert guarded_.first == "bubble1"
    assert guarded_.then == "primed"
    assert guarded_.guard_text == "not Bernoulli(p = pBubble)"
    assert type(guarded_.guard).__name__ == "UnaryOperation"
    assert members[2].guard_text is None
    assert members[3].guard_text == "sample.invalid"


def test_24_perform_action_with_body_and_bound_parameters():
    model = _parse(
        """\
package P {
    part def Station {
        perform action run : Proc { in part :>> cart = cartridge; }
    }
}
"""
    )
    perform_ = model.members[0].members[0].members[0]
    assert perform_.modifiers == ["perform"]
    assert perform_.kind == "action"
    assert perform_.name == "run"
    assert perform_.has_body is True
    bound_ = perform_.members[0]
    assert bound_.modifiers == ["in"]
    assert bound_.kind == "part"
    assert bound_.redefines == ["cart"]
    assert bound_.value_text == "cartridge"


def test_25_not_in_expressions():
    model = _parse("package P { attribute :>> ok = not sample.invalid; }")
    attribute_ = model.members[0].members[0]
    assert type(attribute_.value).__name__ == "UnaryOperation"
    assert attribute_.value.operator == "not"
    assert attribute_.value.operand.path == ["sample", "invalid"]
