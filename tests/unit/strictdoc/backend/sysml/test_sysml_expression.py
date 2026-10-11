import pytest

from strictdoc.backend.sysml.expression import (
    BinaryOperation,
    BooleanLiteral,
    Conditional,
    FeatureReference,
    Invocation,
    NumberLiteral,
    StringLiteral,
    SysMLExpressionError,
    UnaryOperation,
    parse_expression,
)


def test_01_number_with_unit():
    expression = parse_expression("40 [s]")
    assert expression == NumberLiteral(value=40.0, text="40", unit="s")


def test_02_precedence_of_multiplication_over_addition():
    expression = parse_expression("1 + 2 * 3")
    assert isinstance(expression, BinaryOperation)
    assert expression.operator == "+"
    assert isinstance(expression.right, BinaryOperation)
    assert expression.right.operator == "*"


def test_03_power_is_right_associative_and_binds_tighter_than_unary_minus():
    expression = parse_expression("-2 ** 3 ** 2")
    assert isinstance(expression, UnaryOperation)
    power_ = expression.operand
    assert isinstance(power_, BinaryOperation)
    assert power_.operator == "**"
    assert isinstance(power_.right, BinaryOperation)


def test_04_comparisons_and_boolean_operators():
    expression = parse_expression("a >= 1 and not b or c")
    assert isinstance(expression, BinaryOperation)
    assert expression.operator == "or"


def test_05_feature_references_with_quotes_and_qualified_names():
    assert parse_expression("pump::flow") == FeatureReference(name="pump::flow")
    assert parse_expression("'Pump A'.flow") == FeatureReference(
        name="Pump A.flow"
    ) or parse_expression("'Pump A'.flow") == FeatureReference(
        name="Pump A::flow"
    )


def test_06_invocation_with_positional_and_named_arguments():
    expression = parse_expression("Calc(1, rate = 2 [s])")
    assert isinstance(expression, Invocation)
    assert expression.callee == "Calc"
    assert expression.arguments[0].name is None
    assert expression.arguments[1].name == "rate"
    assert expression.arguments[1].value == NumberLiteral(
        value=2.0, text="2", unit="s"
    )


def test_07_conditional_expression():
    expression = parse_expression("if x > 1 ? 2 else 3")
    assert isinstance(expression, Conditional)
    assert expression.consequence == NumberLiteral(value=2.0, text="2")


def test_08_literals():
    assert parse_expression('"text"') == StringLiteral(value="text")
    assert parse_expression("true") == BooleanLiteral(value=True)


@pytest.mark.parametrize("text", ["", "1 +", "a b", "(1", "1 $ 2", "f(1 2)"])
def test_09_invalid_expressions_raise(text):
    with pytest.raises(SysMLExpressionError):
        parse_expression(text)
