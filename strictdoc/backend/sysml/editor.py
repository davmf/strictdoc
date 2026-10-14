"""
Edits SysML design packages in place.

The web UI edits a design element in one of two ways:

- Tables: the DETAILS row of the element and one MEMBERS row per direct
  attribute or usage. A changed row rewrites only the declaration head of
  its member: the text before the body `{`, or the whole declaration up to
  `;`. A deleted row removes the member text, including its body. A new row
  is inserted before the closing `}` of the element.
- Source: the text of the element, from its first `#` annotation to its
  closing `}` or `;`.

The whole file can also be replaced. Text outside the edited ranges stays
the same byte for byte, including comments and layout.

Every edit returns the new file text and parses it again to check the edit.
validate_text() then reads the text as a StrictDoc document. The caller
writes the file and rebuilds the traceability index.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple, Union

from strictdoc.backend.sysml.grammar import SYSML_GRAMMAR
from strictdoc.backend.sysml.model import (
    SysMLAttribute,
    SysMLElement,
    SysMLMember,
    SysMLModel,
    SysMLPackage,
    SysMLSpan,
)
from strictdoc.backend.sysml.parser import SysMLParseError, SysMLParser
from strictdoc.backend.sysml.reader import (
    SysMLReader,
    specialization_properties,
    split_units,
)
from strictdoc.helpers.exception import StrictDocException

SysMLDeclaration = Union[SysMLElement, SysMLAttribute]

KIND_COLUMN = "Kind"
MODIFIERS_COLUMN = "Modifiers"
NAME_COLUMN = "Name"
SHORT_NAME_COLUMN = "Short name"
TYPE_COLUMN = "Type"
SUBSETS_COLUMN = "Subsets"
REDEFINES_COLUMN = "Redefines"
MULTIPLICITY_COLUMN = "Multiplicity"
VALUE_COLUMN = "Value"
UNITS_COLUMN = "Units"
ANNOTATIONS_COLUMN = "Annotations"

DETAILS_COLUMNS: Tuple[str, ...] = (
    KIND_COLUMN,
    MODIFIERS_COLUMN,
    NAME_COLUMN,
    SHORT_NAME_COLUMN,
    TYPE_COLUMN,
    SUBSETS_COLUMN,
    REDEFINES_COLUMN,
    MULTIPLICITY_COLUMN,
    VALUE_COLUMN,
    UNITS_COLUMN,
    ANNOTATIONS_COLUMN,
)
MEMBERS_COLUMNS: Tuple[str, ...] = (
    KIND_COLUMN,
    MODIFIERS_COLUMN,
    NAME_COLUMN,
    TYPE_COLUMN,
    SUBSETS_COLUMN,
    REDEFINES_COLUMN,
    MULTIPLICITY_COLUMN,
    VALUE_COLUMN,
    UNITS_COLUMN,
)
NEW_ROW_ID = "new"

# Specialization columns and the operator that the editor writes for each.
_SPECIALIZATION_OPERATORS: Tuple[Tuple[str, str], ...] = (
    (TYPE_COLUMN, ":"),
    (SUBSETS_COLUMN, ":>"),
    (REDEFINES_COLUMN, ":>>"),
)
_INDENT = "    "
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _grammar_choices(rule_name: str) -> FrozenSet[str]:
    """Return the keywords of a grammar rule such as `Modifier`."""
    match = re.search(
        rf"^{rule_name}:\n(.*?)^;", SYSML_GRAMMAR, re.MULTILINE | re.DOTALL
    )
    assert match is not None, rule_name
    return frozenset(re.findall(r"'([^']+)'", match.group(1)))


DECLARATION_KINDS: FrozenSet[str] = _grammar_choices("DeclKind")
MODIFIERS: FrozenSet[str] = _grammar_choices("Modifier")
# All words that the grammar matches as keywords. A name that equals one of
# them is written quoted.
_KEYWORDS: FrozenSet[str] = frozenset(
    word_
    for word_ in re.findall(r"'([A-Za-z]+)'", SYSML_GRAMMAR)
    if _IDENTIFIER_PATTERN.fullmatch(word_) is not None
)


class SysMLEditError(StrictDocException):
    """An edit that cannot be applied or that gives an invalid file."""


@dataclass
class SysMLTableRow:
    """
    One MEMBERS row from the editor form.

    row_id is the index of the member in editable_members(), or NEW_ROW_ID.
    values maps each of MEMBERS_COLUMNS to its text.
    """

    row_id: str
    values: Dict[str, str]
    is_deleted: bool = False

    def is_empty(self) -> bool:
        return all(len(value_.strip()) == 0 for value_ in self.values.values())


@dataclass
class _Edit:
    """Replace data[start:end] with replacement. Offsets are in bytes."""

    start: int
    end: int
    replacement: str


@dataclass
class _TableEditPlan:
    edits: List[_Edit] = field(default_factory=list)
    added_declarations: List[str] = field(default_factory=list)
    expected_member_count: int = 0


def find_element(model: SysMLModel, byte_offset: int) -> Optional[SysMLElement]:
    """Return the element whose member span starts at byte_offset."""
    return _find_element_in(model.members, byte_offset)


def editable_members(element: SysMLElement) -> List[SysMLDeclaration]:
    """Direct members of an element that the MEMBERS table shows."""
    return [
        member_
        for member_ in element.members
        if isinstance(member_, (SysMLElement, SysMLAttribute))
    ]


def declaration_kind(declaration: SysMLDeclaration) -> str:
    if isinstance(declaration, SysMLAttribute):
        return declaration.kind if declaration.kind is not None else ""
    if declaration.is_definition:
        return f"{declaration.kind} def"
    return declaration.kind


def details_values(element: SysMLElement) -> Dict[str, str]:
    """The DETAILS row of an element, one text per DETAILS_COLUMNS entry."""
    return _head_values(element, DETAILS_COLUMNS)


def member_values(declaration: SysMLDeclaration) -> Dict[str, str]:
    """The MEMBERS row of a member, one text per MEMBERS_COLUMNS entry."""
    return _head_values(declaration, MEMBERS_COLUMNS)


def element_source(file_text: str, element: SysMLElement) -> str:
    """
    The source text of an element, as the Source tab shows it.

    The first line starts at the element. The other lines lose the
    indentation of the line where the element starts.
    """
    data = file_text.encode("utf-8")
    span = _member_span(element)
    text = data[span.byte_start : span.byte_end].decode("utf-8")
    indent = _line_indent(data, span.byte_start)
    lines = text.split("\n")
    dedented = lines[:1] + [
        line_[len(indent) :] if line_.startswith(indent) else line_.lstrip()
        for line_ in lines[1:]
    ]
    return "\n".join(dedented)


def normalize_source(text: str) -> str:
    """
    Normalize text that comes from a browser form.

    Line endings become LF, non-breaking spaces become spaces, trailing
    whitespace is removed from each line, and blank lines at both ends are
    removed.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    lines = [line_.rstrip() for line_ in text.split("\n")]
    while len(lines) > 0 and len(lines[0]) == 0:
        lines.pop(0)
    while len(lines) > 0 and len(lines[-1]) == 0:
        lines.pop()
    return "\n".join(lines)


def tables_changed(
    element: SysMLElement,
    details: Dict[str, str],
    rows: List[SysMLTableRow],
) -> bool:
    if _row_differs(details, details_values(element)):
        return True
    members = editable_members(element)
    for row_ in rows:
        if row_.row_id == NEW_ROW_ID:
            if not row_.is_deleted and not row_.is_empty():
                return True
            continue
        if row_.is_deleted:
            return True
        member = _member_by_row_id(members, row_.row_id)
        if _row_differs(row_.values, member_values(member)):
            return True
    return False


def apply_element_edit(
    file_text: str,
    element: SysMLElement,
    details: Dict[str, str],
    rows: List[SysMLTableRow],
    source: str,
) -> Optional[str]:
    """
    Apply the editor form of one element and return the new file text.

    Returns None when nothing has changed. Raises SysMLEditError when both
    the tables and the source have changed, or when the edit is invalid.
    """
    is_source_changed = normalize_source(source) != normalize_source(
        element_source(file_text, element)
    )
    is_tables_changed = tables_changed(element, details, rows)
    if is_source_changed and is_tables_changed:
        raise SysMLEditError(
            "Both the tables and the source have changed. "
            "Edit either the tables or the source, not both."
        )
    if is_source_changed:
        return apply_source_edit(file_text, element, source)
    if is_tables_changed:
        return apply_table_edits(file_text, element, details, rows)
    return None


def apply_source_edit(
    file_text: str, element: SysMLElement, source: str
) -> str:
    """Replace the source text of an element and return the new file text."""
    normalized = normalize_source(source)
    if len(normalized) == 0:
        raise SysMLEditError(
            "The source of the element is empty. "
            "Delete the element in the source of its parent instead."
        )
    data = file_text.encode("utf-8")
    span = _member_span(element)
    indent = _line_indent(data, span.byte_start)
    lines = normalized.split("\n")
    indented = lines[:1] + [
        indent + line_ if len(line_) > 0 else line_ for line_ in lines[1:]
    ]
    replacement = "\n".join(indented)
    new_text = _apply_edits(
        data, [_Edit(span.byte_start, span.byte_end, replacement)]
    )
    _check_single_element(
        new_text,
        span.byte_start,
        span.byte_start + len(replacement.encode("utf-8")),
    )
    return new_text


def apply_table_edits(
    file_text: str,
    element: SysMLElement,
    details: Dict[str, str],
    rows: List[SysMLTableRow],
) -> str:
    """Apply the DETAILS and MEMBERS rows and return the new file text."""
    data = file_text.encode("utf-8")
    plan = _plan_member_edits(data, element, rows)

    element_span = _member_span(element)
    is_head_changed = _row_differs(details, details_values(element))
    head = (
        _head_text(details, DETAILS_COLUMNS, element)
        if is_head_changed
        else _original_head_text(data, element)
    )
    indent = _line_indent(data, element_span.byte_start)
    child_indent = indent + _INDENT

    if element.body_span is not None:
        if is_head_changed:
            plan.edits.append(
                _Edit(
                    element_span.byte_start,
                    element.body_span.byte_start,
                    head + " ",
                )
            )
        if len(plan.added_declarations) > 0:
            plan.edits.append(
                _insertion_before_closing_brace(
                    data,
                    element.body_span,
                    plan.added_declarations,
                    indent,
                    child_indent,
                )
            )
    elif len(plan.added_declarations) > 0:
        body_lines = [
            child_indent + declaration_
            for declaration_ in plan.added_declarations
        ]
        plan.edits.append(
            _Edit(
                element_span.byte_start,
                element_span.byte_end,
                head + " {\n" + "\n".join(body_lines) + "\n" + indent + "}",
            )
        )
    elif is_head_changed:
        plan.edits.append(
            _Edit(element_span.byte_start, element_span.byte_end, head + ";")
        )

    new_text = _apply_edits(data, plan.edits)
    _check_table_result(
        new_text, element_span.byte_start, plan.expected_member_count
    )
    return new_text


def validate_text(
    text: str, file_path: Optional[str], relative_path: str
) -> None:
    """
    Read the text as a StrictDoc document. Raise SysMLEditError on errors.

    This catches syntax errors and reader errors, for example a `verify`
    statement outside an element. The traceability checks, such as unknown
    requirement UIDs, need the whole project and are done by the caller.
    """
    try:
        SysMLReader.read_from_string(
            text, file_path=file_path, relative_path=relative_path
        )
    except StrictDocException as exception_:
        raise SysMLEditError(exception_.to_print_message()) from exception_


def _find_element_in(
    members: List[SysMLMember], byte_offset: int
) -> Optional[SysMLElement]:
    for member_ in members:
        if isinstance(member_, SysMLElement):
            if _member_span(member_).byte_start == byte_offset:
                return member_
            found = _find_element_in(member_.members, byte_offset)
            if found is not None:
                return found
        elif isinstance(member_, SysMLPackage):
            found = _find_element_in(member_.members, byte_offset)
            if found is not None:
                return found
    return None


def _member_span(declaration: SysMLDeclaration) -> SysMLSpan:
    if declaration.member_span is not None:
        return declaration.member_span
    return declaration.span


def _head_values(
    declaration: SysMLDeclaration, columns: Tuple[str, ...]
) -> Dict[str, str]:
    value, units = split_units(declaration.value_text)
    values: Dict[str, str] = {
        KIND_COLUMN: declaration_kind(declaration),
        MODIFIERS_COLUMN: " ".join(declaration.modifiers),
        NAME_COLUMN: declaration.name or "",
        SHORT_NAME_COLUMN: declaration.short_name or "",
        TYPE_COLUMN: "",
        SUBSETS_COLUMN: "",
        REDEFINES_COLUMN: "",
        MULTIPLICITY_COLUMN: declaration.multiplicity or "",
        VALUE_COLUMN: value,
        UNITS_COLUMN: units,
        ANNOTATIONS_COLUMN: " ".join(declaration.annotations),
    }
    for label_, text_ in specialization_properties(declaration.specializations):
        values[label_] = text_ or ""
    return {column_: values[column_] for column_ in columns}


def _row_differs(values: Dict[str, str], original: Dict[str, str]) -> bool:
    for column_, original_value_ in original.items():
        if values.get(column_, "").strip() != original_value_.strip():
            return True
    return False


def _member_by_row_id(
    members: List[SysMLDeclaration], row_id: str
) -> SysMLDeclaration:
    if not row_id.isdigit() or int(row_id) >= len(members):
        raise SysMLEditError(
            f"The member row '{row_id}' does not exist. "
            "Cancel and open the editor again."
        )
    return members[int(row_id)]


def _plan_member_edits(
    data: bytes, element: SysMLElement, rows: List[SysMLTableRow]
) -> _TableEditPlan:
    members = editable_members(element)
    plan = _TableEditPlan()
    seen_row_ids: List[str] = []
    for row_ in rows:
        if row_.row_id == NEW_ROW_ID:
            if row_.is_deleted or row_.is_empty():
                continue
            plan.added_declarations.append(
                _head_text(row_.values, MEMBERS_COLUMNS, None) + ";"
            )
            continue
        if row_.row_id in seen_row_ids:
            raise SysMLEditError(
                f"The member row '{row_.row_id}' is submitted twice."
            )
        seen_row_ids.append(row_.row_id)
        member = _member_by_row_id(members, row_.row_id)
        span = _member_span(member)
        if row_.is_deleted:
            start, end = _deletion_range(data, span)
            plan.edits.append(_Edit(start, end, ""))
            continue
        if not _row_differs(row_.values, member_values(member)):
            continue
        head = _head_text(row_.values, MEMBERS_COLUMNS, member)
        if isinstance(member, SysMLElement) and member.body_span is not None:
            plan.edits.append(
                _Edit(span.byte_start, member.body_span.byte_start, head + " ")
            )
        else:
            plan.edits.append(_Edit(span.byte_start, span.byte_end, head + ";"))
    deleted_count = sum(
        1 for row_ in rows if row_.row_id != NEW_ROW_ID and row_.is_deleted
    )
    plan.expected_member_count = (
        len(members) - deleted_count + len(plan.added_declarations)
    )
    return plan


def _head_text(
    values: Dict[str, str],
    columns: Tuple[str, ...],
    original: Optional[SysMLDeclaration],
) -> str:
    """
    Build a declaration head from a table row.

    Properties that the row has no column for, such as the short name in
    the MEMBERS table or a `default` value, are taken from the original
    declaration.
    """

    def value_of(column: str) -> str:
        if column in columns:
            return values.get(column, "").strip()
        if original is None:
            return ""
        return _head_values(original, (column,))[column].strip()

    parts: List[str] = []
    for annotation_ in value_of(ANNOTATIONS_COLUMN).split():
        parts.append("#" + annotation_.lstrip("#"))

    for modifier_ in value_of(MODIFIERS_COLUMN).split():
        if modifier_ not in MODIFIERS:
            raise SysMLEditError(
                f"Unknown modifier '{modifier_}'. "
                f"Use one of: {', '.join(sorted(MODIFIERS))}."
            )
        parts.append(modifier_)

    kind = value_of(KIND_COLUMN)
    if len(kind) > 0:
        kind_words = kind.split()
        if kind_words[0] not in DECLARATION_KINDS or kind_words[1:] not in (
            [],
            ["def"],
        ):
            raise SysMLEditError(
                f"Unknown kind '{kind}'. Use one of: "
                f"{', '.join(sorted(DECLARATION_KINDS))}, "
                "optionally followed by 'def'."
            )
        parts.append(" ".join(kind_words))

    short_name = value_of(SHORT_NAME_COLUMN)
    if len(short_name) > 0:
        parts.append(f"<{_name_text(short_name)}>")
    name = value_of(NAME_COLUMN)
    if len(name) > 0:
        parts.append(_name_text(name))

    has_specialization = False
    for column_, operator_ in _SPECIALIZATION_OPERATORS:
        targets = value_of(column_)
        if len(targets) > 0:
            parts.append(f"{operator_} {targets}")
            has_specialization = True

    if len(kind) == 0 and len(value_of(MODIFIERS_COLUMN)) == 0:
        if not has_specialization:
            raise SysMLEditError(
                "A member without a kind needs a modifier or a "
                f"specialization, for example 'in' or ':>>': "
                f"'{name}'."
            )

    multiplicity = value_of(MULTIPLICITY_COLUMN)
    if len(multiplicity) > 0:
        if not multiplicity.startswith("["):
            multiplicity = f"[{multiplicity}]"
        parts.append(multiplicity)

    value = value_of(VALUE_COLUMN)
    units = value_of(UNITS_COLUMN)
    if len(value) > 0:
        parts.append(f"= {value} [{units}]" if len(units) > 0 else f"= {value}")
    elif len(units) > 0:
        raise SysMLEditError(f"Units '{units}' need a value: '{name}'.")

    if original is not None and original.default_text is not None:
        parts.append(f"default = {original.default_text}")
    return " ".join(parts)


def _original_head_text(data: bytes, element: SysMLElement) -> str:
    span = _member_span(element)
    end = (
        element.body_span.byte_start
        if element.body_span is not None
        else span.byte_end
    )
    head = data[span.byte_start : end].decode("utf-8").rstrip()
    if element.body_span is None and head.endswith(";"):
        head = head[:-1].rstrip()
    return head


def _name_text(name: str) -> str:
    if (
        _IDENTIFIER_PATTERN.fullmatch(name) is not None
        and name not in _KEYWORDS
    ):
        return name
    escaped = name.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _line_start(data: bytes, offset: int) -> int:
    return data.rfind(b"\n", 0, offset) + 1


def _line_indent(data: bytes, offset: int) -> str:
    """The leading whitespace of the line that contains offset."""
    line = data[_line_start(data, offset) : offset].decode("utf-8")
    return line[: len(line) - len(line.lstrip())]


def _deletion_range(data: bytes, span: SysMLSpan) -> Tuple[int, int]:
    """
    The range to delete for a member.

    When the member is alone on its lines, the whole lines are deleted.
    """
    line_start = _line_start(data, span.byte_start)
    line_end = data.find(b"\n", span.byte_end)
    if line_end == -1:
        line_end = len(data)
    is_alone = (
        len(data[line_start : span.byte_start].strip()) == 0
        and len(data[span.byte_end : line_end].strip()) == 0
    )
    if is_alone:
        return line_start, min(line_end + 1, len(data))
    end = span.byte_end
    while end < len(data) and data[end : end + 1] in (b" ", b"\t"):
        end += 1
    return span.byte_start, end


def _insertion_before_closing_brace(
    data: bytes,
    body_span: SysMLSpan,
    declarations: List[str],
    indent: str,
    child_indent: str,
) -> _Edit:
    closing_brace = body_span.byte_end - 1
    assert data[closing_brace : closing_brace + 1] == b"}"
    line_start = _line_start(data, closing_brace)
    lines = "".join(
        child_indent + declaration_ + "\n" for declaration_ in declarations
    )
    if len(data[line_start:closing_brace].strip()) == 0:
        return _Edit(line_start, line_start, lines)
    # The brace shares its line with other text, as in `part p { }`.
    start = closing_brace
    while start > 0 and data[start - 1 : start] in (b" ", b"\t"):
        start -= 1
    return _Edit(start, closing_brace, "\n" + lines + indent)


def _apply_edits(data: bytes, edits: List[_Edit]) -> str:
    ordered = sorted(edits, key=lambda edit_: edit_.start, reverse=True)
    previous_start = len(data)
    for edit_ in ordered:
        assert edit_.end <= previous_start, "Overlapping SysML edits."
        data = (
            data[: edit_.start]
            + edit_.replacement.encode("utf-8")
            + data[edit_.end :]
        )
        previous_start = edit_.start
    return data.decode("utf-8")


def _parse(text: str) -> SysMLModel:
    try:
        return SysMLParser.parse_string(text)
    except SysMLParseError as exception_:
        raise SysMLEditError(exception_.to_print_message()) from exception_


def _check_single_element(text: str, byte_start: int, byte_end: int) -> None:
    """Check that the new source is exactly one element."""
    model = _parse(text)
    element = find_element(model, byte_start)
    if element is None or _member_span(element).byte_end != byte_end:
        raise SysMLEditError(
            "The source must contain exactly one SysML element, such as "
            "'part def Pump { ... }'. "
            "To change more than one element, edit the SysML source of the "
            "document."
        )


def _check_table_result(
    text: str, byte_start: int, expected_member_count: int
) -> None:
    """Check that every row is read back as an attribute or a usage."""
    model = _parse(text)
    element = find_element(model, byte_start)
    if element is None:
        raise SysMLEditError(
            "The DETAILS row does not give a valid SysML element."
        )
    if len(editable_members(element)) != expected_member_count:
        raise SysMLEditError(
            "A MEMBERS row does not give a valid SysML declaration. "
            "Check the kind, modifiers, names and values."
        )
