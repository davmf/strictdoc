"""
Public parser API for the SysML v2 subset.

Import this module to parse SysML text into the typed model defined in
model.py. The model is what external tools, such as the Halcyon simulation
generator, should walk. They should not import the textX grammar directly.

Usage:

    from strictdoc.backend.sysml.parser import SysMLParser

    model = SysMLParser.parse_file("model/design/pump.sysml")
    for member_ in model.members:
        ...

parse_string() and parse_file() return a SysMLModel. Syntax errors raise
SysMLParseError, a StrictDocException that carries the file path and line.

Notes for consumers:

- Names are unquoted: `'SYS-THR-001'` becomes SYS-THR-001. Qualified names
  are joined with `::`.
- Doc comments are stored as text without the ` * ` decoration.
- Expression text is kept raw (value_text, condition_text, result_text) and
  also parsed (value, condition, result_expression). A parsed field is None
  when the text is outside the supported expression syntax.
- Unknown members inside a body become SysMLOpaque members.
"""

import bisect
import re
import textwrap
from typing import Any, List, Optional, Tuple

from textx import TextXSyntaxError, metamodel_from_str

from strictdoc.backend.sysml.expression import (
    Expression,
    SysMLExpressionError,
    parse_expression,
)
from strictdoc.backend.sysml.grammar import SYSML_GRAMMAR
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
    SysMLMember,
    SysMLMetadataUsage,
    SysMLModel,
    SysMLOpaque,
    SysMLPackage,
    SysMLPerform,
    SysMLRequireConstraint,
    SysMLSatisfy,
    SysMLSpan,
    SysMLSpecialization,
    SysMLSuccession,
    SysMLThen,
    SysMLVerify,
)
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.file_system import file_open_read_utf8

__all__ = [
    "SysMLParseError",
    "SysMLParser",
]

_NAME_SEGMENT_PATTERN = re.compile(r"'(?:[^'\\]|\\.)*'|[A-Za-z_][A-Za-z0-9_]*")


class SysMLParseError(StrictDocException):
    """A syntax error in a SysML file. The message contains file and line."""


class SysMLParser:
    """
    Parser for the SysML v2 subset. Use parse_string() or parse_file().

    The textX metamodel is built once, when this module is imported.
    """

    _metamodel: Any = metamodel_from_str(SYSML_GRAMMAR, autokwd=True)

    @staticmethod
    def parse_string(text: str, file_path: Optional[str] = None) -> SysMLModel:
        """
        Parse SysML text into a SysMLModel.

        file_path is only used for error messages and stored on the model.
        Raises SysMLParseError on a syntax error.
        """
        assert isinstance(text, str), text
        try:
            textx_model: Any = SysMLParser._metamodel.model_from_str(text)
        except TextXSyntaxError as exception_:
            raise SysMLParseError(
                _format_syntax_error(exception_, file_path)
            ) from exception_

        context = _ConversionContext(text, file_path)
        members = [
            _convert_member(member_, context) for member_ in textx_model.members
        ]
        return SysMLModel(
            file_path=file_path,
            members=members,
            source_text=text,
        )

    @staticmethod
    def parse_file(file_path: str) -> SysMLModel:
        """Read a SysML file as UTF-8 (BOM stripped) and parse it."""
        with file_open_read_utf8(file_path) as file_:
            content = file_.read()
        return SysMLParser.parse_string(content, file_path=file_path)


def _unquote_name(raw_name: str) -> str:
    if len(raw_name) >= 2 and raw_name[0] == "'" and raw_name[-1] == "'":
        return re.sub(r"\\(.)", r"\1", raw_name[1:-1])
    return raw_name


_QUOTED_SEGMENT_PATTERN = re.compile(r"'((?:[^'\\]|\\.)*)'")


def _qualified_name(raw_name: str) -> str:
    """
    Reference text with quoted segments unquoted and separators kept.

    `'SYS-1'` becomes SYS-1, and `baseSteady.configuration` stays as written.
    """
    return _QUOTED_SEGMENT_PATTERN.sub(
        lambda match_: re.sub(r"\\(.)", r"\1", match_.group(1)), raw_name
    )


def _reference_path(raw_name: str) -> List[str]:
    """Unquoted segments of a reference, in order, across `::` and `.`."""
    return [
        _unquote_name(segment_)
        for segment_ in _NAME_SEGMENT_PATTERN.findall(raw_name)
    ]


def _doc_text(raw_comment: str) -> str:
    """
    Strip `/*` and `*/`, then the leading ` * ` decoration of each line.

    Leading and trailing blank lines are removed. Other lines keep their
    internal indentation.
    """
    content = raw_comment[2:-2]
    lines: List[str] = []
    for line_ in content.split("\n"):
        stripped = line_.lstrip()
        if stripped.startswith("*"):
            body = stripped[1:]
            if body.startswith(" "):
                body = body[1:]
        else:
            body = stripped
        lines.append(body.rstrip())
    return _trim_blank_lines("\n".join(lines))


def _trim_blank_lines(text: str) -> str:
    lines = text.split("\n")
    while len(lines) > 0 and lines[0].strip() == "":
        lines.pop(0)
    while len(lines) > 0 and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines)


def _block_inner_text(raw_block: str) -> str:
    """Return the text between the outer braces, dedented and trimmed."""
    inner = raw_block[1:-1]
    trimmed = _trim_blank_lines(inner)
    dedented = textwrap.dedent(trimmed)
    return "\n".join(line_.rstrip() for line_ in dedented.split("\n"))


def _normalize_expression_text(raw_text: str) -> str:
    return raw_text.strip()


def _units_of(value_text: Optional[str]) -> Optional[str]:
    if value_text is None:
        return None
    match = re.search(r"\[([^\]]*)\]\s*$", value_text)
    if match is None:
        return None
    return match.group(1).strip()


def _parse_expression_or_none(text: str) -> Optional[Expression]:
    try:
        return parse_expression(text)
    except SysMLExpressionError:
        return None


class _ConversionContext:
    """Maps textX character positions to line, column and byte offsets."""

    def __init__(self, source_text: str, file_path: Optional[str]) -> None:
        self.source_text: str = source_text
        self.file_path: Optional[str] = file_path
        self._line_starts: List[int] = [0]
        for index_, character_ in enumerate(source_text):
            if character_ == "\n":
                self._line_starts.append(index_ + 1)
        self._byte_offsets: Optional[List[int]] = None
        if not source_text.isascii():
            offsets: List[int] = [0]
            total = 0
            for character_ in source_text:
                total += len(character_.encode("utf-8"))
                offsets.append(total)
            self._byte_offsets = offsets

    def span_of(self, textx_object: Any) -> SysMLSpan:
        start: int = textx_object._tx_position
        end: int = textx_object._tx_position_end
        # textX positions can include surrounding whitespace.
        while start < end and self.source_text[start].isspace():
            start += 1
        while end > start and self.source_text[end - 1].isspace():
            end -= 1
        line_start, col_start = self._line_col(start)
        line_end, col_end = self._line_col(max(end - 1, start))
        return SysMLSpan(
            line_start=line_start,
            col_start=col_start,
            line_end=line_end,
            col_end=col_end + (1 if end > start else 0),
            byte_start=self._byte_offset(start),
            byte_end=self._byte_offset(end),
        )

    def source_of(self, textx_object: Any) -> str:
        span_start: int = textx_object._tx_position
        span_end: int = textx_object._tx_position_end
        return self.source_text[span_start:span_end].strip()

    def _line_col(self, position: int) -> Tuple[int, int]:
        line_index = bisect.bisect_right(self._line_starts, position) - 1
        column = position - self._line_starts[line_index] + 1
        return line_index + 1, column

    def _byte_offset(self, position: int) -> int:
        if self._byte_offsets is None:
            return position
        return self._byte_offsets[position]


def _format_syntax_error(
    exception_: TextXSyntaxError, file_path: Optional[str]
) -> str:
    location = file_path if file_path is not None else "<string>"
    return (
        f"Could not parse SysML file: {location}, "
        f"line {getattr(exception_, 'line', None)}, "
        f"column {getattr(exception_, 'col', None)}: "
        "unexpected input. Check the SysML v2 syntax at this location."
    )


def _convert_member(
    member_obj: Any, context: _ConversionContext
) -> SysMLMember:
    class_name = type(member_obj).__name__
    if class_name == "Opaque":
        return SysMLOpaque(
            text=member_obj.text.strip(),
            source_text=context.source_of(member_obj),
            span=context.span_of(member_obj),
        )
    if class_name != "Member":
        raise AssertionError(f"Unexpected SysML member: {class_name}")

    annotations = [
        _unquote_name(annotation_.name)
        for annotation_ in member_obj.annotations
    ]
    core = member_obj.core
    return _convert_core(core, context, annotations)


def _convert_core(
    core: Any, context: _ConversionContext, annotations: List[str]
) -> SysMLMember:
    class_name = type(core).__name__
    span = context.span_of(core)
    if class_name == "Package":
        return _convert_package(core, context)
    if class_name == "Import":
        return SysMLImport(
            visibility=core.visibility if core.visibility else None,
            target=core.target.strip(),
            span=span,
        )
    if class_name == "DocComment":
        return SysMLDocComment(
            name=_unquote_name(core.name) if core.name else None,
            text=_doc_text(core.text),
            span=span,
        )
    if class_name == "BlockComment":
        return SysMLBlockComment(
            name=_unquote_name(core.name) if core.name else None,
            text=_doc_text(core.text),
            span=span,
        )
    if class_name == "LineNote":
        return SysMLLineNote(text=core.text.rstrip(), span=span)
    if class_name == "Dependency":
        return SysMLDependency(
            sources=[_qualified_name(raw_) for raw_ in core.sources],
            targets=[_qualified_name(raw_) for raw_ in core.targets],
            annotations=annotations,
            span=span,
        )
    if class_name == "Satisfy":
        return SysMLSatisfy(
            requirement=_qualified_name(core.requirement),
            by=_qualified_name(core.by) if core.by else None,
            annotations=annotations,
            span=span,
            by_path=_reference_path(core.by) if core.by else [],
            source_text=context.source_of(core),
        )
    if class_name == "Verify":
        return SysMLVerify(
            requirement=_qualified_name(core.requirement),
            annotations=annotations,
            span=span,
            source_text=context.source_of(core),
        )
    if class_name == "Allocate":
        return SysMLAllocate(
            source=_qualified_name(core.source),
            target=_qualified_name(core.target),
            annotations=annotations,
            span=span,
            source_path=_reference_path(core.source),
            target_path=_reference_path(core.target),
        )
    if class_name == "Succession":
        guard_text: Optional[str] = None
        guard: Optional[Expression] = None
        if core.is_guarded:
            guard_text = _normalize_expression_text(core.guard)
            guard = _parse_expression_or_none(guard_text)
        return SysMLSuccession(
            first=_qualified_name(core.first),
            then=_qualified_name(core.then),
            annotations=annotations,
            span=span,
            first_path=_reference_path(core.first),
            then_path=_reference_path(core.then),
            guard_text=guard_text,
            guard=guard,
        )
    if class_name == "Then":
        return SysMLThen(
            target=_qualified_name(core.target),
            target_path=_reference_path(core.target),
            annotations=annotations,
            span=span,
        )
    if class_name == "BehaviourControl":
        return SysMLBehaviourControl(
            kind=core.kind,
            name=_unquote_name(core.name) if core.name else None,
            annotations=annotations,
            span=span,
        )
    if class_name == "IfThen":
        condition_text = _normalize_expression_text(core.condition)
        return SysMLIfThen(
            condition_text=condition_text,
            condition=_parse_expression_or_none(condition_text),
            target=_qualified_name(core.target),
            target_path=_reference_path(core.target),
            annotations=annotations,
            span=span,
        )
    if class_name == "ElseThen":
        return SysMLElseThen(
            target=_qualified_name(core.target),
            target_path=_reference_path(core.target),
            annotations=annotations,
            span=span,
        )
    if class_name == "Perform":
        return SysMLPerform(
            target=_qualified_name(core.target),
            target_path=_reference_path(core.target),
            annotations=annotations,
            span=span,
        )
    if class_name == "MetadataUsage":
        body_text: Optional[str] = None
        if core.block is not None:
            body_text = _block_inner_text(context.source_of(core.block))
        return SysMLMetadataUsage(
            name=_unquote_name(core.name),
            body_text=body_text,
            annotations=annotations,
            span=span,
        )
    if class_name == "MemberRequireConstraint":
        return SysMLRequireConstraint(
            text=_block_inner_text(context.source_of(core.block)),
            span=span,
        )
    if class_name == "Declaration":
        return _convert_declaration(core, context, annotations)
    raise AssertionError(f"Unexpected SysML member core: {class_name}")


def _convert_package(core: Any, context: _ConversionContext) -> SysMLPackage:
    return SysMLPackage(
        name=_unquote_name(core.name) if core.name else None,
        short_name=(
            _unquote_name(core.short_name.name) if core.short_name else None
        ),
        members=_convert_body_members(core.body, context),
        span=context.span_of(core),
    )


def _convert_body_members(
    body: Any, context: _ConversionContext
) -> List[SysMLMember]:
    return [_convert_member(member_, context) for member_ in body.members]


def _convert_specializations(
    specializations: Any,
) -> List[SysMLSpecialization]:
    result: List[SysMLSpecialization] = []
    for specialization_ in specializations:
        result.append(
            SysMLSpecialization(
                operator=specialization_.operator,
                targets=[
                    _qualified_name(target_)
                    for target_ in specialization_.targets
                ],
                targets_text=", ".join(specialization_.targets),
            )
        )
    return result


def _redefined_names(specializations: List[SysMLSpecialization]) -> List[str]:
    names: List[str] = []
    for specialization_ in specializations:
        if specialization_.operator in (":>>", "redefines"):
            names.extend(specialization_.targets)
    return names


def _convert_declaration(
    core: Any, context: _ConversionContext, annotations: List[str]
) -> SysMLMember:
    kind: Optional[str] = core.kind if core.kind else None
    modifiers: List[str] = list(core.modifiers)
    is_definition = bool(core.is_def)
    short_name = (
        _unquote_name(core.short_name.name) if core.short_name else None
    )
    name = _unquote_name(core.name) if core.name else None
    specializations: List[SysMLSpecialization] = []
    if core.head_specialization is not None:
        specializations.extend(
            _convert_specializations([core.head_specialization])
        )
    specializations.extend(_convert_specializations(core.specializations))
    redefines = _redefined_names(specializations)
    multiplicity = core.multiplicity.text if core.multiplicity else None
    value_text: Optional[str] = None
    if core.value is not None:
        value_text = _normalize_expression_text(core.value.text)
    default_text: Optional[str] = None
    if core.default is not None:
        default_text = _normalize_expression_text(core.default.text)
    span = context.span_of(core)
    source_text = context.source_of(core)
    is_abstract = "abstract" in modifiers

    if (
        (kind in (None, "attribute"))
        and not is_definition
        and (core.body is None)
    ):
        type_specializations = [
            specialization_
            for specialization_ in specializations
            if specialization_.operator == ":"
        ]
        type_names: List[str] = []
        type_text: Optional[str] = None
        if len(type_specializations) > 0:
            type_names = type_specializations[0].targets
            type_text = type_specializations[0].targets_text
        return SysMLAttribute(
            name=name,
            short_name=short_name,
            modifiers=modifiers,
            specializations=specializations,
            type_names=type_names,
            type_text=type_text,
            multiplicity=multiplicity,
            value_text=value_text,
            value=(
                _parse_expression_or_none(value_text)
                if value_text is not None
                else None
            ),
            units=_units_of(value_text),
            annotations=annotations,
            span=span,
            source_text=source_text,
            is_abstract=is_abstract,
            redefines=redefines,
            default_text=default_text,
            default_value=(
                _parse_expression_or_none(default_text)
                if default_text is not None
                else None
            ),
        )

    members: List[SysMLMember] = []
    result_text: Optional[str] = None
    result_expression: Optional[Expression] = None
    if core.body is not None:
        members = _convert_body_members(core.body, context)
        if core.body.result is not None:
            result_text = _normalize_expression_text(core.body.result.text)
            result_expression = _parse_expression_or_none(result_text)
    docs: List[str] = [
        member_.text
        for member_ in members
        if isinstance(member_, SysMLDocComment)
    ]
    return SysMLElement(
        kind=kind if kind is not None else "",
        is_definition=is_definition,
        modifiers=modifiers,
        short_name=short_name,
        name=name,
        specializations=specializations,
        multiplicity=multiplicity,
        value_text=value_text,
        value=(
            _parse_expression_or_none(value_text)
            if value_text is not None
            else None
        ),
        annotations=annotations,
        has_body=core.body is not None,
        members=members,
        doc=docs[0] if len(docs) > 0 else None,
        docs=docs,
        result_text=result_text,
        result_expression=result_expression,
        span=span,
        source_text=source_text,
        is_abstract=is_abstract,
        redefines=redefines,
        default_text=default_text,
        default_value=(
            _parse_expression_or_none(default_text)
            if default_text is not None
            else None
        ),
    )
