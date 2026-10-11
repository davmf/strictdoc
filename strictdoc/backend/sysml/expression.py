"""
Expression tree for SysML attribute values, constraints and calc bodies.

parse_expression(text) turns the raw expression text into the tree below.
The tree is built from plain dataclasses, so it can be pickled and walked
without textX.

Supported syntax: numeric literals with an optional unit in brackets
(`40 [s]`), string and boolean literals, feature references (`a`, `'a b'`,
`a::b`, `a.b`), unary `- + not`, binary `** ^ * / % + - < <= > >= == != and
or xor`, parentheses, invocations `Calc(arg = value, ...)` and conditionals
`if c ? a else b`.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Union


class SysMLExpressionError(Exception):
    """Raised when expression text does not follow the supported syntax."""


@dataclass
class NumberLiteral:
    value: float
    text: str
    unit: Optional[str] = None


@dataclass
class StringLiteral:
    value: str


@dataclass
class BooleanLiteral:
    value: bool


@dataclass
class FeatureReference:
    name: str


@dataclass
class UnaryOperation:
    operator: str
    operand: "Expression"


@dataclass
class BinaryOperation:
    operator: str
    left: "Expression"
    right: "Expression"


@dataclass
class Argument:
    name: Optional[str]
    value: "Expression"


@dataclass
class Invocation:
    callee: str
    arguments: List[Argument] = field(default_factory=list)


@dataclass
class Conditional:
    condition: "Expression"
    consequence: "Expression"
    alternative: "Expression"


Expression = Union[
    NumberLiteral,
    StringLiteral,
    BooleanLiteral,
    FeatureReference,
    UnaryOperation,
    BinaryOperation,
    Invocation,
    Conditional,
]


def parse_expression(text: str) -> Expression:
    """
    Parse raw SysML expression text into an expression tree.

    Raises SysMLExpressionError if the text is outside the supported syntax.
    """
    if not isinstance(text, str):
        raise SysMLExpressionError(f"expression must be a str: {text!r}")
    return _ExpressionParser(text).parse()


_TOKEN_PATTERN = re.compile(
    r"""
    (?P<space>\s+)
  | (?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<quoted>'(?:[^'\\]|\\.)*')
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<operator>\*\*|::|==|!=|<=|>=|\^|\*|/|%|\+|-|<|>|\(|\)|,|=|\?|\[|\]|\.)
    """,
    re.VERBOSE,
)

_KEYWORD_OPERATORS = {"and", "or", "xor", "not"}
_BINARY_PRECEDENCE: List[List[str]] = [
    ["or", "xor"],
    ["and"],
    ["==", "!="],
    ["<", "<=", ">", ">="],
    ["+", "-"],
    ["*", "/", "%"],
]


@dataclass
class _Token:
    kind: str
    text: str


def _tokenize(text: str) -> List[_Token]:
    tokens: List[_Token] = []
    position = 0
    while position < len(text):
        match = _TOKEN_PATTERN.match(text, position)
        if match is None:
            raise SysMLExpressionError(
                f"unexpected character {text[position]!r} in expression: "
                f"{text!r}"
            )
        position = match.end()
        kind = match.lastgroup
        if kind == "space":
            continue
        assert kind is not None
        tokens.append(_Token(kind=kind, text=match.group(kind)))
    return tokens


def _unquote(raw_text: str) -> str:
    if len(raw_text) >= 2 and raw_text[0] == raw_text[-1] == "'":
        return re.sub(r"\\(.)", r"\1", raw_text[1:-1])
    return raw_text


class _ExpressionParser:
    def __init__(self, text: str) -> None:
        self._text: str = text
        self._tokens: List[_Token] = _tokenize(text)
        self._index: int = 0

    def parse(self) -> Expression:
        if len(self._tokens) == 0:
            raise SysMLExpressionError("empty expression")
        expression = self._parse_conditional()
        if self._index != len(self._tokens):
            raise SysMLExpressionError(
                f"unexpected token {self._peek_text()!r} in expression: "
                f"{self._text!r}"
            )
        return expression

    def _peek(self) -> Optional[_Token]:
        if self._index < len(self._tokens):
            return self._tokens[self._index]
        return None

    def _peek_text(self) -> str:
        token = self._peek()
        return token.text if token is not None else "<end>"

    def _advance(self) -> _Token:
        token = self._peek()
        if token is None:
            raise SysMLExpressionError(
                f"unexpected end of expression: {self._text!r}"
            )
        self._index += 1
        return token

    def _expect(self, text: str) -> None:
        token = self._advance()
        if token.text != text:
            raise SysMLExpressionError(
                f"expected {text!r} but found {token.text!r} in expression: "
                f"{self._text!r}"
            )

    def _parse_conditional(self) -> Expression:
        token = self._peek()
        if token is not None and token.text == "if":
            self._advance()
            condition = self._parse_binary(0)
            self._expect("?")
            consequence = self._parse_conditional()
            self._expect("else")
            alternative = self._parse_conditional()
            return Conditional(
                condition=condition,
                consequence=consequence,
                alternative=alternative,
            )
        return self._parse_binary(0)

    def _parse_binary(self, level: int) -> Expression:
        if level >= len(_BINARY_PRECEDENCE):
            return self._parse_unary()
        left = self._parse_binary(level + 1)
        operators = _BINARY_PRECEDENCE[level]
        while True:
            token = self._peek()
            if token is None or token.text not in operators:
                return left
            self._advance()
            right = self._parse_binary(level + 1)
            left = BinaryOperation(operator=token.text, left=left, right=right)

    def _parse_unary(self) -> Expression:
        token = self._peek()
        if token is not None and token.text in ("-", "+", "not"):
            self._advance()
            return UnaryOperation(
                operator=token.text, operand=self._parse_unary()
            )
        return self._parse_power()

    def _parse_power(self) -> Expression:
        # Power binds tighter than unary minus: -2 ** 2 is -(2 ** 2).
        base = self._parse_primary()
        token = self._peek()
        if token is not None and token.text in ("**", "^"):
            self._advance()
            exponent = self._parse_unary()
            return BinaryOperation(
                operator=token.text, left=base, right=exponent
            )
        return base

    def _parse_primary(self) -> Expression:
        token = self._advance()
        if token.kind == "number":
            return NumberLiteral(
                value=float(token.text),
                text=token.text,
                unit=self._parse_optional_unit(),
            )
        if token.kind == "string":
            return StringLiteral(value=token.text[1:-1])
        if token.text in ("true", "false"):
            return BooleanLiteral(value=token.text == "true")
        if token.text == "(":
            inner = self._parse_conditional()
            self._expect(")")
            return inner
        if token.kind in ("name", "quoted"):
            return self._parse_reference(token)
        raise SysMLExpressionError(
            f"unexpected token {token.text!r} in expression: {self._text!r}"
        )

    def _parse_optional_unit(self) -> Optional[str]:
        token = self._peek()
        if token is None or token.text != "[":
            return None
        self._advance()
        unit_parts: List[str] = []
        while True:
            unit_token = self._advance()
            if unit_token.text == "]":
                break
            unit_parts.append(unit_token.text)
        return "".join(unit_parts)

    def _parse_reference(self, first_token: _Token) -> Expression:
        name_parts: List[str] = [self._segment_text(first_token)]
        while True:
            token = self._peek()
            if token is None or token.text not in ("::", "."):
                break
            self._advance()
            name_parts.append(self._segment_text(self._advance()))
        separator = "::"
        name = name_parts[0]
        for part_ in name_parts[1:]:
            name = f"{name}{separator}{part_}"
        token = self._peek()
        if token is not None and token.text == "(":
            return self._parse_invocation(name)
        return FeatureReference(name=name)

    @staticmethod
    def _segment_text(token: _Token) -> str:
        if token.kind == "quoted":
            return _unquote(token.text)
        if token.kind == "name" and token.text in _KEYWORD_OPERATORS:
            raise SysMLExpressionError(
                f"keyword {token.text!r} cannot be used as a name"
            )
        return token.text

    def _parse_invocation(self, callee: str) -> Expression:
        self._expect("(")
        arguments: List[Argument] = []
        token = self._peek()
        if token is not None and token.text == ")":
            self._advance()
            return Invocation(callee=callee, arguments=arguments)
        while True:
            argument_name: Optional[str] = None
            token = self._peek()
            next_index = self._index + 1
            if (
                token is not None
                and token.kind in ("name", "quoted")
                and next_index < len(self._tokens)
                and self._tokens[next_index].text == "="
            ):
                argument_name = self._segment_text(self._advance())
                self._advance()
            value = self._parse_conditional()
            arguments.append(Argument(name=argument_name, value=value))
            separator = self._advance()
            if separator.text == ")":
                break
            if separator.text != ",":
                raise SysMLExpressionError(
                    f"expected ',' or ')' in invocation: {self._text!r}"
                )
        return Invocation(callee=callee, arguments=arguments)
