"""
Writes requirements packages in the canonical SysML layout.

The layout follows the Halcyon conventions document:

- 4-space indentation, one level per package or requirement body;
- doc comments in ` * ` style, with the closing ` */` aligned on the
  comment's ` * ` column;
- blank lines between top-level blocks of a package body (doc comments,
  imports, nested packages, requirements, dependencies), but not inside a
  requirement body;
- attributes and the require constraint directly after the statement;
- the item version, if any, as the first line of a requirement body, and the
  traced version, if any, in the body of a dependency (see versioning.py).
- the value of an enum-typed attribute as a literal qualified by its type,
  e.g. `Status::'Needs work'` (see choices.py).

Reading a canonical file and writing it back produces identical text.

Not preserved: line notes (`//`), block comments (`/* */`) that are not doc
comments, and the original order of blocks, which is normalised.

The writer refuses to write autogen documents, i.e. design packages. It
skips the generated diagram node.
"""

import hashlib
import os
import re
from typing import Dict, List, Optional, Sequence, Set, Union

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sdoc.models.reference import ParentReqReference
from strictdoc.backend.sysml import choices, node_data
from strictdoc.backend.sysml.versioning import (
    ITEM_VERSION_FIELD,
    content_hash,
    item_version_text,
    traced_version_text,
)
from strictdoc.core.document_meta import DocumentMeta
from strictdoc.helpers.cast import assert_cast
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.file_system import file_open_read_utf8

_INDENT = "    "
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RESERVED_FIELD_TITLES = {
    "UID",
    "TITLE",
    "STATEMENT",
    "CONSTRAINT",
    "MID",
    ITEM_VERSION_FIELD,
}


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
                    "\n".join(SysMLWriter._requirement_lines(child_, pad))
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
    def requirement_hash(requirement: SDocNode) -> str:
        """
        The content hash of a requirement: the hash of its canonical text
        without the item version line.
        """
        lines = SysMLWriter._requirement_lines(
            requirement, "", include_version=False
        )
        return content_hash("\n".join(lines))

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
        include_version: bool = True,
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

        item_version = node_data.get_item_version(requirement)
        if include_version and item_version is not None:
            lines.append(body_pad + item_version_text(item_version))

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

        choice_types = _choice_types(requirement)
        written_titles: Set[str] = set()
        for attribute_name_, type_text_ in attribute_types.items():
            field_title_ = node_data.attribute_field_title(attribute_name_)
            written_titles.add(field_title_)
            lines.append(
                body_pad
                + SysMLWriter._attribute_text(
                    _name_text(attribute_name_),
                    type_text_,
                    _attribute_value(
                        values_by_title.get(field_title_),
                        type_text_,
                        choice_types.get(field_title_),
                    ),
                )
            )
        for field_title_, value_ in values_by_title.items():
            if field_title_ in written_titles:
                continue
            choice_type = choice_types.get(field_title_)
            lines.append(
                body_pad
                + SysMLWriter._attribute_text(
                    _name_text(
                        node_data.attribute_name_from_field_title(field_title_)
                    ),
                    choice_type,
                    _attribute_value(value_, choice_type, choice_type),
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
            head = (
                f"{pad}{prefix}dependency from {_quote_name(child_uid)} "
                f"to {_quote_name(relation_.ref_uid)}"
            )
            traced_version = node_data.get_traced_version(relation_)
            if traced_version is None:
                lines.append(head + ";")
                continue
            lines.append(head + " {")
            lines.append(pad + _INDENT + traced_version_text(traced_version))
            lines.append(pad + "}")
        return lines


class SysMLTrackerWriter:
    """
    Writes a requirements document of the tracker layout (see tracker.py)
    back to its files: the tracker file, one file per section (folder) and
    one file per requirement (item).

    - A tracker or folder file has its metadata, its doc comments and one
      `public import '<ID>'::*;` per child, in document order.
    - An item file has the imports of the item, the requirement and the
      dependencies of the requirement.
    - A requirement without a UID gets the tracker prefix and the next free
      number. A new section gets the ID `<prefix>-F-<TITLE>`.
    - A new item file gets the imports of the first item of the tracker, or
      an import of the tracker. `#derivation` adds an import of
      RequirementDerivation.
    - Files whose text does not change are not written. Files of the tracker
      that are no longer part of it are deleted.
    """

    @staticmethod
    def write_to_files(document: SDocDocument) -> List[str]:
        """
        Write the files of the document. Returns the paths that were
        written or deleted.
        """
        files_by_path = SysMLTrackerWriter.render(document)
        tracker_data = assert_cast(
            node_data.get_tracker(document), node_data.TrackerData
        )
        tracker_directory = os.path.dirname(tracker_data.tracker.file_path)
        changed_paths: List[str] = []
        for path_, text_ in files_by_path.items():
            if _read_text(path_) == text_:
                continue
            with open(path_, "w", encoding="utf8", newline="") as file_:
                file_.write(text_)
            changed_paths.append(path_)
        for path_ in tracker_data.file_paths:
            if path_ in files_by_path or not os.path.isfile(path_):
                continue
            if not os.path.abspath(path_).startswith(
                os.path.abspath(tracker_directory) + os.sep
            ):
                continue
            os.remove(path_)
            changed_paths.append(path_)
        tracker_data.file_paths = list(files_by_path)
        return changed_paths

    @staticmethod
    def render(document: SDocDocument) -> Dict[str, str]:
        """
        The text of every file of the document, by path. Gives missing IDs
        to requirements and sections, and records the file of each node.
        """
        if document.autogen:
            raise StrictDocException(
                "SysML design packages are read only and cannot be written: "
                f"{document.title}."
            )
        tracker_data = assert_cast(
            node_data.get_tracker(document), node_data.TrackerData
        )
        state = _TrackerWriteState(document, tracker_data)
        files_by_path: Dict[str, str] = {}
        child_ids = SysMLTrackerWriter._write_children(
            document.section_contents, state, files_by_path
        )
        head_lines = [_INDENT + tracker_data.metadata_text]
        head_lines.extend(_text_lines(document.section_contents, _INDENT))
        tracker_path = tracker_data.tracker.file_path
        files_by_path[tracker_path] = _package_text(
            tracker_data.tracker.file_id, head_lines, child_ids
        )
        # The tracker file is first, then folders and items in document
        # order.
        return {
            tracker_path: files_by_path[tracker_path],
            **{
                path_: text_
                for path_, text_ in files_by_path.items()
                if path_ != tracker_path
            },
        }

    @staticmethod
    def _write_children(
        children: Sequence[object],
        state: "_TrackerWriteState",
        files_by_path: Dict[str, str],
    ) -> List[str]:
        child_ids: List[str] = []
        for child_ in children:
            if not isinstance(child_, SDocNode):
                continue
            if node_data.is_diagram(child_) or child_.node_type == "TEXT":
                continue
            if child_.node_type == "SECTION":
                child_ids.append(
                    SysMLTrackerWriter._write_folder(
                        child_, state, files_by_path
                    )
                )
            elif child_.node_type == "REQUIREMENT":
                child_ids.append(
                    SysMLTrackerWriter._write_item(child_, state, files_by_path)
                )
            else:
                raise StrictDocException(
                    "The node type cannot be written to a SysML file: "
                    f"{child_.node_type}."
                )
        return child_ids

    @staticmethod
    def _write_folder(
        section: SDocNode,
        state: "_TrackerWriteState",
        files_by_path: Dict[str, str],
    ) -> str:
        title = _field_text(section, "TITLE") or ""
        folder_file = node_data.get_folder(section)
        if folder_file is not None:
            folder_id = folder_file.file_id
            folder_path = folder_file.file_path
        else:
            folder_id = state.new_folder_id(title)
            folder_path = state.new_file_path(folder_id)
        child_ids = SysMLTrackerWriter._write_children(
            section.section_contents, state, files_by_path
        )
        escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
        head_lines = [
            (
                f"{_INDENT}@StrictDocWorkspace::Folder "
                f'{{ title = "{escaped_title}"; }}'
            )
        ]
        head_lines.extend(_text_lines(section.section_contents, _INDENT))
        text = _package_text(folder_id, head_lines, child_ids)
        files_by_path[folder_path] = text
        node_data.set_folder(
            section,
            node_data.TrackerFile(
                file_id=folder_id,
                file_path=folder_path,
                source_hash=_text_hash(text),
            ),
        )
        return folder_id

    @staticmethod
    def _write_item(
        requirement: SDocNode,
        state: "_TrackerWriteState",
        files_by_path: Dict[str, str],
    ) -> str:
        uid = _field_text(requirement, "UID")
        item_file = node_data.get_item_file(requirement)
        if uid is None:
            uid = (
                item_file.file_id
                if item_file is not None
                else state.new_item_id()
            )
            requirement.set_field_value(
                field_name="UID", form_field_index=0, value=uid
            )
        if item_file is not None and item_file.file_id == uid:
            item_path = item_file.file_path
            imports = node_data.get_imports(requirement)
        else:
            item_path = state.new_file_path(uid)
            imports = (
                node_data.get_imports(requirement)
                if item_file is not None
                else state.default_imports
            )
        dependency_lines = SysMLWriter._dependency_lines(
            requirement, _INDENT, state.document
        )
        if node_data.get_derivation_prefix(state.document) and not any(
            "RequirementDerivation" in import_ for import_ in imports
        ):
            imports = imports + ["private import RequirementDerivation::*;"]
        blocks: List[str] = []
        if len(imports) > 0:
            blocks.append("\n".join(_INDENT + import_ for import_ in imports))
        blocks.append(
            "\n".join(SysMLWriter._requirement_lines(requirement, _INDENT))
        )
        if len(dependency_lines) > 0:
            blocks.append("\n".join(dependency_lines))
        text = _package_lines_text(uid, blocks)
        files_by_path[item_path] = text
        node_data.set_imports(requirement, imports)
        node_data.set_item_file(
            requirement,
            node_data.TrackerFile(
                file_id=uid, file_path=item_path, source_hash=_text_hash(text)
            ),
        )
        return uid


class _TrackerWriteState:
    def __init__(
        self, document: SDocDocument, tracker_data: node_data.TrackerData
    ) -> None:
        self.document: SDocDocument = document
        self.tracker_data: node_data.TrackerData = tracker_data
        self.directory: str = os.path.dirname(tracker_data.tracker.file_path)
        tracker_id = tracker_data.tracker.file_id
        self.prefix: str = (
            tracker_data.prefix
            if tracker_data.prefix is not None and len(tracker_data.prefix) > 0
            else re.sub(r"^TRK-", "", tracker_id)
        )
        self.used_ids: Set[str] = {tracker_id}
        self.default_imports: List[str] = [
            f"private import {_quote_name(tracker_id)}::*;"
        ]
        found_item_imports = False
        for node_ in document.iterate_nodes():
            if not isinstance(node_, SDocNode):
                continue
            uid_ = _field_text(node_, "UID")
            if uid_ is not None:
                self.used_ids.add(uid_)
            item_file_ = node_data.get_item_file(node_)
            if item_file_ is not None:
                self.used_ids.add(item_file_.file_id)
                if not found_item_imports:
                    self.default_imports = node_data.get_imports(node_)
                    found_item_imports = True
            folder_file_ = node_data.get_folder(node_)
            if folder_file_ is not None:
                self.used_ids.add(folder_file_.file_id)
        self.known_paths: Set[str] = set(tracker_data.file_paths)

    def new_item_id(self) -> str:
        pattern = re.compile(re.escape(self.prefix) + r"-(\d+)$")
        highest = 0
        for id_ in self.used_ids:
            match_ = pattern.match(id_)
            if match_ is not None:
                highest = max(highest, int(match_.group(1)))
        new_id = f"{self.prefix}-{highest + 1:03d}"
        self.used_ids.add(new_id)
        return new_id

    def new_folder_id(self, title: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").upper()
        base_id = f"{self.prefix}-F-{slug if len(slug) > 0 else 'FOLDER'}"
        new_id = base_id
        counter = 2
        while new_id in self.used_ids:
            new_id = f"{base_id}-{counter}"
            counter += 1
        self.used_ids.add(new_id)
        return new_id

    def new_file_path(self, file_id: str) -> str:
        path = os.path.join(self.directory, f"{file_id}.sysml")
        if path not in self.known_paths and os.path.exists(path):
            raise StrictDocException(
                f"Cannot write the SysML item '{file_id}': {path} exists "
                "and is not part of this tracker."
            )
        return path


def _package_text(
    package_id: str, head_lines: List[str], child_ids: List[str]
) -> str:
    blocks = ["\n".join(head_lines)]
    if len(child_ids) > 0:
        blocks.append(
            "\n".join(
                f"{_INDENT}public import {_quote_name(id_)}::*;"
                for id_ in child_ids
            )
        )
    return _package_lines_text(package_id, blocks)


def _package_lines_text(package_id: str, blocks: List[str]) -> str:
    """`package '<ID>' { ... }` with blank lines between the blocks."""
    return (
        f"package {_quote_name(package_id)} {{\n"
        + "\n\n".join(blocks)
        + "\n}\n"
    )


def _text_lines(children: Sequence[object], pad: str) -> List[str]:
    lines: List[str] = []
    for child_ in children:
        if (
            isinstance(child_, SDocNode)
            and child_.node_type == "TEXT"
            and not node_data.is_diagram(child_)
        ):
            lines.extend(_doc_block(_field_text(child_, "STATEMENT"), pad))
    return lines


def _read_text(path: str) -> Optional[str]:
    if not os.path.isfile(path):
        return None
    with file_open_read_utf8(path) as file_:
        return file_.read()


def _text_hash(text: str) -> str:
    """The same hash as tracker.text_hash() and node_data.source_hash()."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _quote_name(raw_name: str) -> str:
    escaped = raw_name.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _name_text(raw_name: str) -> str:
    if _IDENTIFIER_PATTERN.fullmatch(raw_name) is not None:
        return raw_name
    return _quote_name(raw_name)


def _choice_types(requirement: SDocNode) -> Dict[str, str]:
    if requirement.ng_document_reference is None:
        return {}
    document = requirement.ng_document_reference.get_document()
    if not isinstance(document, SDocDocument):
        return {}
    return node_data.get_choice_types(document)


def _attribute_value(
    value: Optional[str],
    type_text: Optional[str],
    choice_type: Optional[str],
) -> Optional[str]:
    """
    The value text of an attribute. The value of an enum-typed attribute is
    a bare literal name, which is qualified by its type.
    """
    if (
        value is None
        or type_text is None
        or choice_type is None
        or type_text.strip() != choice_type
    ):
        return value
    return choices.literal_reference(choice_type, value)


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
