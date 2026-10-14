"""
Writes requirements packages in the canonical SysML layout.

The layout follows the Halcyon conventions document:

- 4-space indentation, one level per package or requirement body;
- doc comments in ` * ` style, with the closing ` */` aligned on the
  comment's ` * ` column;
- blank lines between top-level blocks of a package body (doc comments,
  imports, nested packages, requirements, dependencies), but not inside a
  requirement body;
- attributes and the require constraint directly after the statement.

Reading a canonical file and writing it back produces identical text.

Not preserved: line notes (`//`), block comments (`/* */`) that are not doc
comments, and the original order of blocks, which is normalised.

The writer refuses to write autogen documents, i.e. design packages. It
skips the generated diagram node.
"""

import re
from typing import Dict, List, Optional, Sequence, Set, Union

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sdoc.models.reference import ParentReqReference
from strictdoc.backend.sysml import node_data
from strictdoc.core.document_meta import DocumentMeta
from strictdoc.helpers.cast import assert_cast
from strictdoc.helpers.exception import StrictDocException

_INDENT = "    "
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RESERVED_FIELD_TITLES = {"UID", "TITLE", "STATEMENT", "CONSTRAINT", "MID"}


class SysMLWriter:
    @staticmethod
    def write_to_file(document: SDocDocument) -> None:
        document_meta: DocumentMeta = assert_cast(document.meta, DocumentMeta)
        content = SysMLWriter.write(document)
        with open(
            document_meta.input_doc_full_path, "w", encoding="utf8"
        ) as output_file:
            output_file.write(content)

    @staticmethod
    def write(document: SDocDocument) -> str:
        if document.autogen:
            raise StrictDocException(
                "SysML design packages are read only and cannot be written: "
                f"{document.title}."
            )
        blocks = SysMLWriter._container_blocks(
            document,
            document.section_contents,
            indent_level=1,
            document=document,
        )
        lines = [f"package {_quote_name(document.title)} {{"]
        if len(blocks) > 0:
            lines.append("\n\n".join(blocks))
        lines.append("}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _container_blocks(
        container: Union[SDocDocument, SDocNode],
        children: Sequence[object],
        indent_level: int,
        document: SDocDocument,
    ) -> List[str]:
        pad = _INDENT * indent_level
        blocks: List[str] = []

        children = [
            child_
            for child_ in children
            if not (
                isinstance(child_, SDocNode) and node_data.is_diagram(child_)
            )
        ]
        for child_ in children:
            if isinstance(child_, SDocNode) and child_.node_type == "TEXT":
                blocks.append(
                    "\n".join(_doc_block(_field_text(child_, "STATEMENT"), pad))
                )

        imports = node_data.get_imports(container)
        if len(imports) > 0:
            blocks.append("\n".join(f"{pad}{import_}" for import_ in imports))

        dependency_lines: List[str] = []
        for child_ in children:
            if not isinstance(child_, SDocNode):
                continue
            if child_.node_type == "TEXT":
                continue
            if child_.node_type == "REQUIREMENT":
                blocks.append(
                    "\n".join(
                        SysMLWriter._requirement_lines(child_, pad, document)
                    )
                )
                dependency_lines.extend(
                    SysMLWriter._dependency_lines(child_, pad, document)
                )
            elif child_.node_type == "SECTION":
                blocks.append(SysMLWriter._section_block(child_, pad, document))
            else:
                raise StrictDocException(
                    "The node type cannot be written to a SysML file: "
                    f"{child_.node_type}."
                )

        if len(dependency_lines) > 0:
            blocks.append("\n".join(dependency_lines))
        return blocks

    @staticmethod
    def _section_block(
        section: SDocNode, pad: str, document: SDocDocument
    ) -> str:
        title = _field_text(section, "TITLE") or ""
        child_pad = pad + _INDENT
        lines = [f"{pad}package {_quote_name(title)} {{"]
        blocks = SysMLWriter._container_blocks(
            section,
            section.section_contents,
            indent_level=len(child_pad) // len(_INDENT),
            document=document,
        )
        if len(blocks) > 0:
            lines.append("\n\n".join(blocks))
        lines.append(f"{pad}}}")
        return "\n".join(lines)

    @staticmethod
    def _requirement_lines(
        requirement: SDocNode,
        pad: str,
        document: SDocDocument,  # noqa: ARG004
    ) -> List[str]:
        head = "requirement"
        uid = _field_text(requirement, "UID")
        if uid is not None:
            head += f" <{_quote_name(uid)}>"
        title = _field_text(requirement, "TITLE")
        if title is not None:
            head += f" {_quote_name(title)}"
        body_pad = pad + _INDENT
        lines = [f"{pad}{head} {{"]

        statement = _field_text(requirement, "STATEMENT")
        if statement is not None:
            lines.extend(_doc_block(statement, body_pad))

        attribute_types: Dict[str, Optional[str]] = (
            node_data.get_attribute_types(requirement)
        )
        values_by_title: Dict[str, str] = {}
        for field_title_ in requirement.ordered_fields_lookup:
            if field_title_ in _RESERVED_FIELD_TITLES:
                continue
            value_ = _field_text(requirement, field_title_)
            if value_ is not None:
                values_by_title[field_title_] = value_

        written_titles: Set[str] = set()
        for attribute_name_, type_text_ in attribute_types.items():
            field_title_ = node_data.attribute_field_title(attribute_name_)
            written_titles.add(field_title_)
            lines.append(
                body_pad
                + SysMLWriter._attribute_text(
                    _name_text(attribute_name_),
                    type_text_,
                    values_by_title.get(field_title_),
                )
            )
        for field_title_, value_ in values_by_title.items():
            if field_title_ in written_titles:
                continue
            lines.append(
                body_pad
                + SysMLWriter._attribute_text(
                    _name_text(
                        node_data.attribute_name_from_field_title(field_title_)
                    ),
                    None,
                    value_,
                )
            )

        constraint = _field_text(requirement, "CONSTRAINT")
        if constraint is not None:
            lines.append(f"{body_pad}require constraint {{")
            constraint_pad = body_pad + _INDENT
            for line_ in constraint.split("\n"):
                lines.append(f"{constraint_pad}{line_}".rstrip())
            lines.append(f"{body_pad}}}")

        lines.append(f"{pad}}}")
        return lines

    @staticmethod
    def _attribute_text(
        name_text: str, type_text: Optional[str], value: Optional[str]
    ) -> str:
        text = f"attribute {name_text}"
        if type_text is not None and len(type_text) > 0:
            text += f" : {type_text}"
        if value is not None and len(value) > 0:
            text += f" = {value}"
        return text + ";"

    @staticmethod
    def _dependency_lines(
        requirement: SDocNode, pad: str, document: SDocDocument
    ) -> List[str]:
        child_uid = _field_text(requirement, "UID")
        lines: List[str] = []
        for relation_ in requirement.relations:
            if not isinstance(relation_, ParentReqReference):
                continue
            if child_uid is None:
                raise StrictDocException(
                    "A requirement without UID cannot have a dependency "
                    "in a SysML file: "
                    f"{document.title}."
                )
            prefix = (
                "#derivation "
                if node_data.get_derivation_prefix(document)
                else ""
            )
            lines.append(
                f"{pad}{prefix}dependency from {_quote_name(child_uid)} "
                f"to {_quote_name(relation_.ref_uid)};"
            )
        return lines


def _quote_name(raw_name: str) -> str:
    escaped = raw_name.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _name_text(raw_name: str) -> str:
    if _IDENTIFIER_PATTERN.fullmatch(raw_name) is not None:
        return raw_name
    return _quote_name(raw_name)


def _field_text(node: SDocNode, field_title: str) -> Optional[str]:
    fields = node.ordered_fields_lookup.get(field_title)
    if fields is None or len(fields) == 0:
        return None
    text = fields[0].get_text_value().rstrip("\n")
    if len(text) == 0:
        return None
    return text


def _doc_block(text: Optional[str], pad: str) -> List[str]:
    lines = [f"{pad}doc /*"]
    if text is not None:
        for line_ in text.split("\n"):
            lines.append(f"{pad} * {line_}".rstrip())
    lines.append(f"{pad} */")
    return lines
