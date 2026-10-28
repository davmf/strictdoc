"""
Choice fields: requirement attributes typed by an enumeration.

An attribute such as

    attribute status : Status = Status::'Waiting for approval';

is an enum-typed attribute when its value is a literal of its own type.
StrictDoc shows the value as the bare literal name, `Waiting for approval`,
and writes it back qualified by the type.

The literals of an enumeration are known only when the `enum def` has been
read, and it is often in another file, e.g. a library package. So the
reader records the enum-typed fields of each requirements package, and the
enum definitions of each file. After the traceability index is built,
apply_choice_fields() resolves the type of each enum-typed field and turns
the field into a SingleChoice field with the literals as its options. The
edit form shows a SingleChoice field as a drop-down list.

apply_choice_fields() finds a type by its qualified name, or by a name that
a wildcard import of the package (`private import Lib::Choices::*;`) makes
visible.
"""

import re
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.grammar_element import (
    GrammarElementFieldSingleChoice,
)
from strictdoc.backend.sysml import node_data
from strictdoc.backend.sysml.model import (
    SysMLElement,
    SysMLMember,
    SysMLModel,
    SysMLPackage,
)

if TYPE_CHECKING:
    from strictdoc.core.traceability_index import TraceabilityIndex

EnumDefinitions = Dict[Tuple[str, ...], List[str]]

_NAME_PATTERN = r"'(?:[^'\\]|\\.)*'|[A-Za-z_][A-Za-z0-9_]*"
_NAME_SEGMENT_PATTERN = re.compile(_NAME_PATTERN)
_SINGLE_NAME_PATTERN = re.compile(rf"(?:{_NAME_PATTERN})")
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_WILDCARD_IMPORT_PATTERN = re.compile(
    r"^(?:(?:private|public)\s+)?import\s+(.+?)::\*\s*;$"
)


def collect_enum_definitions(model: SysMLModel) -> EnumDefinitions:
    """
    The `enum def` elements of a file, by qualified name (unquoted
    segments), with their literal names in file order.
    """
    definitions: EnumDefinitions = {}
    _collect_enum_definitions(model.members, (), definitions)
    return definitions


def enum_literal(type_text: Optional[str], value_text: str) -> Optional[str]:
    """
    The literal name when value_text is a literal of type_text, e.g.
    `Status::'Needs work'` for the type `Status` gives `Needs work`.
    """
    if type_text is None:
        return None
    prefix = type_text.strip() + "::"
    value = value_text.strip()
    if len(prefix) <= 2 or not value.startswith(prefix):
        return None
    literal_text = value[len(prefix) :]
    if _SINGLE_NAME_PATTERN.fullmatch(literal_text) is None:
        return None
    return _unquote(literal_text)


def literal_reference(type_text: str, literal: str) -> str:
    """The value text of a literal: `Status::'Needs work'`."""
    if _IDENTIFIER_PATTERN.fullmatch(literal) is not None:
        literal_text = literal
    else:
        escaped = literal.replace("\\", "\\\\").replace("'", "\\'")
        literal_text = f"'{escaped}'"
    return f"{type_text}::{literal_text}"


def apply_choice_fields(traceability_index: "TraceabilityIndex") -> None:
    """
    Turn the enum-typed fields of all requirements packages into
    SingleChoice fields. A field keeps its String type when no document
    of the project defines its enumeration.
    """
    document_list: List[SDocDocument] = (
        traceability_index.document_tree.document_list
    )
    definitions: EnumDefinitions = {}
    for document_ in document_list:
        definitions.update(node_data.get_enum_definitions(document_))
    if len(definitions) == 0:
        return
    for document_ in document_list:
        choice_types = node_data.get_choice_types(document_)
        if len(choice_types) == 0 or document_.grammar is None:
            continue
        element = document_.grammar.elements_by_type.get("REQUIREMENT")
        if element is None:
            continue
        namespaces = _imported_namespaces(node_data.get_imports(document_))
        for field_title_, type_text_ in choice_types.items():
            literals = resolve_enum(type_text_, namespaces, definitions)
            if literals is None:
                continue
            for index_, field_ in enumerate(element.fields):
                if field_.title != field_title_:
                    continue
                choice_field = GrammarElementFieldSingleChoice(
                    parent=element,
                    title=field_title_,
                    human_title=field_.human_title,
                    options=literals,
                    required="False",
                )
                element.fields[index_] = choice_field
                element.fields_map[field_title_] = choice_field


def resolve_enum(
    type_text: str,
    namespaces: List[Tuple[str, ...]],
    definitions: EnumDefinitions,
) -> Optional[List[str]]:
    """The literals of the enumeration that type_text names, or None."""
    path = tuple(
        _unquote(segment_)
        for segment_ in _NAME_SEGMENT_PATTERN.findall(type_text)
    )
    if len(path) == 0:
        return None
    for namespace_ in [(), *namespaces]:
        literals = definitions.get(namespace_ + path)
        if literals is not None:
            return list(literals)
    return None


def _collect_enum_definitions(
    members: List[SysMLMember],
    prefix: Tuple[str, ...],
    definitions: EnumDefinitions,
) -> None:
    for member_ in members:
        if isinstance(member_, SysMLPackage):
            if member_.name is None:
                continue
            _collect_enum_definitions(
                member_.members, prefix + (member_.name,), definitions
            )
        elif (
            isinstance(member_, SysMLElement)
            and member_.kind == "enum"
            and member_.is_definition
            and member_.name is not None
        ):
            definitions[prefix + (member_.name,)] = [
                child_.name
                for child_ in member_.members
                if isinstance(child_, SysMLElement)
                and child_.kind == "enum"
                and not child_.is_definition
                and child_.name is not None
            ]


def _imported_namespaces(imports: List[str]) -> List[Tuple[str, ...]]:
    namespaces: List[Tuple[str, ...]] = []
    for import_ in imports:
        match = _WILDCARD_IMPORT_PATTERN.match(import_.strip())
        if match is None:
            continue
        namespaces.append(
            tuple(
                _unquote(segment_)
                for segment_ in _NAME_SEGMENT_PATTERN.findall(match.group(1))
            )
        )
    return namespaces


def _unquote(raw_name: str) -> str:
    if len(raw_name) >= 2 and raw_name[0] == raw_name[-1] == "'":
        return re.sub(r"\\(.)", r"\1", raw_name[1:-1])
    return raw_name
