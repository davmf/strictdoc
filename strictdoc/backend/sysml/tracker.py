"""
Tracker layout: one SysML file per item.

A tracker is a top-level package with `@StrictDocWorkspace::Tracker`
metadata. It includes its folders and items with
`public import '<ID>'::*;`, and a folder (a package with
`@StrictDocWorkspace::Folder` metadata) includes its own children the same
way. Every file holds one top-level package, named by its ID, and the file
name is the ID:

    TRK-SYS/TRK-SYS.sysml         package 'TRK-SYS' { @...Tracker {...}
                                      public import 'SYS-F-THR'::*; }
    TRK-SYS/SYS-F-THR.sysml       package 'SYS-F-THR' { @...Folder {...}
                                      public import 'SYS-THR-001'::*; }
    TRK-SYS/SYS-THR-001.sysml     package 'SYS-THR-001' {
                                      requirement <'SYS-THR-001'> ... }

read_tracker() reads a tracker file and the files it includes.
as_model() turns the result into one SysML model, with the tracker as the
top-level package and the folders as nested packages, so that the readers
of single files can build the document from it.
"""

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

from strictdoc.backend.sysml.model import (
    SysMLDocComment,
    SysMLImport,
    SysMLMember,
    SysMLMetadataUsage,
    SysMLModel,
    SysMLPackage,
    SysMLSpan,
)
from strictdoc.backend.sysml.parser import SysMLParser
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.file_system import file_open_read_utf8

TRACKER_METADATA = "Tracker"
FOLDER_METADATA = "Folder"
WORKSPACE_LIBRARY = "StrictDocWorkspace"

# A tracker file has `@StrictDocWorkspace::Tracker {` (or `@Tracker {`).
_TRACKER_PATTERN = re.compile(
    r"@\s*(?:'?StrictDocWorkspace'?\s*::\s*)?'?Tracker'?\s*\{"
)
# The name of the top-level package of a file.
_PACKAGE_NAME_PATTERN = re.compile(
    r"^\s*(?:(?:public|private|library|standard)\s+)*package\s+"
    r"('(?:[^'\\]|\\.)*'|[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
# `'ID'::*`, `'ID'::**` or `'ID'`
_INCLUDE_PATTERN = re.compile(
    r"^\s*('(?:[^'\\]|\\.)*'|[A-Za-z_][A-Za-z0-9_]*)\s*(?:::\s*\*\*?)?\s*$"
)


@dataclass
class TrackerItem:
    """An item file: one element and the traces it is the client of."""

    item_id: str
    file_path: str
    source_text: str
    package: SysMLPackage
    # The imports of the item package, as written:
    # `private import 'TRK-STK'::*;`.
    imports: List[str]

    def source_hash(self) -> str:
        return text_hash(self.source_text)

    def content_members(self) -> List[SysMLMember]:
        """The members of the item package without its imports."""
        return [
            member_
            for member_ in self.package.members
            if not isinstance(member_, SysMLImport)
        ]


@dataclass
class TrackerFolder:
    folder_id: str
    file_path: str
    source_text: str
    package: SysMLPackage
    title: str
    doc: Optional[SysMLDocComment]
    children: List[Union["TrackerFolder", TrackerItem]] = field(
        default_factory=list
    )


@dataclass
class Tracker:
    tracker_id: str
    file_path: str
    source_text: str
    package: SysMLPackage
    title: str
    kind: Optional[str]
    prefix: Optional[str]
    doc: Optional[SysMLDocComment]
    children: List[Union[TrackerFolder, TrackerItem]] = field(
        default_factory=list
    )

    def items(self) -> List[TrackerItem]:
        result: List[TrackerItem] = []
        _collect_items(self.children, result)
        return result

    def folders(self) -> List[TrackerFolder]:
        result: List[TrackerFolder] = []
        _collect_folders(self.children, result)
        return result

    def files(self) -> List[str]:
        """The tracker file and every file it includes."""
        return (
            [self.file_path]
            + [folder_.file_path for folder_ in self.folders()]
            + [item_.file_path for item_ in self.items()]
        )


class TrackerError(StrictDocException):
    pass


def is_tracker_file(path: str) -> bool:
    """Whether the file holds a tracker package."""
    try:
        with file_open_read_utf8(path) as file_:
            text = file_.read()
    except (OSError, UnicodeDecodeError):
        return False
    return _TRACKER_PATTERN.search(text) is not None


def read_tracker(file_path: str) -> Tracker:
    """
    Read a tracker file and every file it includes.

    Raises TrackerError when an include names no file, when the includes
    form a cycle, when a file is included twice, and when the top-level
    package of a file is not named as the file.
    """
    reader = _TrackerReader(os.path.dirname(os.path.abspath(file_path)))
    return reader.read(os.path.abspath(file_path))


def as_model(tracker: Tracker) -> SysMLModel:
    """
    One SysML model for the whole tracker: a top-level package named by the
    tracker's title, the folders as nested packages named by their titles,
    and in each folder the members of its items, without their imports. The
    members keep the spans of their own files.
    """
    members: List[SysMLMember] = []
    if tracker.doc is not None:
        members.append(tracker.doc)
    members.extend(_as_members(tracker.children))
    package = SysMLPackage(
        name=tracker.title,
        short_name=None,
        members=members,
        span=tracker.package.span,
    )
    return SysMLModel(
        file_path=tracker.file_path,
        members=[package],
        source_text=tracker.source_text,
    )


def items_by_member(tracker: Tracker) -> Dict[int, TrackerItem]:
    """
    The item of every member of the tracker's items, nested members
    included, by id() of the member.
    """
    result: Dict[int, TrackerItem] = {}
    for item_ in tracker.items():
        for member_ in item_.content_members():
            _map_member(member_, item_, result)
    return result


def metadata_value(
    package: SysMLPackage, metadata_name: str, attribute: str
) -> Optional[str]:
    """A string attribute of a workspace metadata usage, unquoted."""
    usage = find_metadata(package, metadata_name)
    if usage is None:
        return None
    raw_value = usage.values.get(attribute)
    if raw_value is None:
        return None
    raw_value = raw_value.strip()
    if len(raw_value) >= 2 and raw_value[0] == '"' and raw_value[-1] == '"':
        raw_value = raw_value[1:-1]
    return raw_value.replace('\\"', '"')


def find_metadata(
    package: SysMLPackage, metadata_name: str
) -> Optional[SysMLMetadataUsage]:
    for member_ in package.members:
        if isinstance(member_, SysMLMetadataUsage) and member_.name in (
            metadata_name,
            f"{WORKSPACE_LIBRARY}::{metadata_name}",
        ):
            return member_
    return None


def text_hash(text: str) -> str:
    """The same hash as node_data.source_hash(), used by the editor."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unquote_name(name: str) -> str:
    if len(name) >= 2 and name[0] == "'" and name[-1] == "'":
        return name[1:-1].replace("\\'", "'")
    return name


class _TrackerReader:
    def __init__(self, tracker_directory: str) -> None:
        self.tracker_directory: str = tracker_directory
        self.included_files: Set[str] = set()
        self.files_by_package_name: Optional[Dict[str, str]] = None

    def read(self, file_path: str) -> Tracker:
        model, package = self._read_package(file_path, expected_id=None)
        tracker_id = _package_name(package, file_path)
        tracker = Tracker(
            tracker_id=tracker_id,
            file_path=file_path,
            source_text=model.source_text,
            package=package,
            title=_title(package, TRACKER_METADATA, tracker_id),
            kind=metadata_value(package, TRACKER_METADATA, "kind"),
            prefix=metadata_value(package, TRACKER_METADATA, "prefix"),
            doc=_first_doc(package),
        )
        self.included_files.add(file_path)
        tracker.children = self._read_children(package, file_path, [file_path])
        return tracker

    def _read_children(
        self,
        package: SysMLPackage,
        file_path: str,
        include_stack: List[str],
    ) -> List[Union[TrackerFolder, TrackerItem]]:
        children: List[Union[TrackerFolder, TrackerItem]] = []
        for member_ in package.members:
            if not isinstance(member_, SysMLImport):
                continue
            if member_.visibility != "public":
                continue
            child_id = _included_id(member_.target)
            if child_id is None:
                continue
            child_path = self._find_file(child_id, file_path, member_.span)
            if child_path in include_stack:
                raise TrackerError(
                    f"Could not read SysML tracker: {file_path}, line "
                    f"{member_.span.line_start}: '{child_id}' includes "
                    "itself through "
                    + " -> ".join(
                        os.path.basename(path_)
                        for path_ in include_stack + [child_path]
                    )
                    + "."
                )
            if child_path in self.included_files:
                raise TrackerError(
                    f"Could not read SysML tracker: {file_path}, line "
                    f"{member_.span.line_start}: '{child_id}' is included "
                    "more than once."
                )
            self.included_files.add(child_path)
            children.append(
                self._read_child(child_id, child_path, include_stack)
            )
        return children

    def _read_child(
        self, child_id: str, child_path: str, include_stack: List[str]
    ) -> Union[TrackerFolder, TrackerItem]:
        model, package = self._read_package(child_path, expected_id=child_id)
        if find_metadata(package, FOLDER_METADATA) is not None:
            folder = TrackerFolder(
                folder_id=child_id,
                file_path=child_path,
                source_text=model.source_text,
                package=package,
                title=_title(package, FOLDER_METADATA, child_id),
                doc=_first_doc(package),
            )
            folder.children = self._read_children(
                package, child_path, include_stack + [child_path]
            )
            return folder
        imports = [
            _import_text(member_)
            for member_ in package.members
            if isinstance(member_, SysMLImport)
        ]
        return TrackerItem(
            item_id=child_id,
            file_path=child_path,
            source_text=model.source_text,
            package=package,
            imports=imports,
        )

    def _read_package(
        self, file_path: str, expected_id: Optional[str]
    ) -> Tuple[SysMLModel, SysMLPackage]:
        model = SysMLParser.parse_file(file_path)
        packages = [
            member_
            for member_ in model.members
            if isinstance(member_, SysMLPackage)
        ]
        if len(packages) != 1:
            raise TrackerError(
                f"Could not read SysML tracker: {file_path}: expected one "
                f"top-level package, found {len(packages)}."
            )
        package = packages[0]
        if expected_id is not None:
            package_name = _package_name(package, file_path)
            if package_name != expected_id:
                raise TrackerError(
                    f"Could not read SysML tracker: {file_path}: the "
                    f"top-level package is '{package_name}', expected "
                    f"'{expected_id}' as in the file name."
                )
        return model, package

    def _find_file(
        self, child_id: str, including_file: str, span: SysMLSpan
    ) -> str:
        """
        The file of an ID: `<ID>.sysml` next to the including file, else the
        file of the tracker directory whose top-level package has this name.
        """
        candidate = os.path.join(
            os.path.dirname(including_file), f"{child_id}.sysml"
        )
        if os.path.isfile(candidate):
            return candidate
        files_by_package_name = self._index_package_names()
        if child_id in files_by_package_name:
            return files_by_package_name[child_id]
        raise TrackerError(
            f"Could not read SysML tracker: {including_file}, line "
            f"{span.line_start}: '{child_id}' names no file: expected "
            f"{child_id}.sysml next to {os.path.basename(including_file)}."
        )

    def _index_package_names(self) -> Dict[str, str]:
        if self.files_by_package_name is not None:
            return self.files_by_package_name
        self.files_by_package_name = {}
        for path_ in _sysml_files(self.tracker_directory):
            with file_open_read_utf8(path_) as file_:
                match = _PACKAGE_NAME_PATTERN.search(file_.read())
            if match is not None:
                self.files_by_package_name.setdefault(
                    unquote_name(match.group(1)), path_
                )
        return self.files_by_package_name


def _package_name(package: SysMLPackage, file_path: str) -> str:
    if package.name is None:
        raise TrackerError(
            f"Could not read SysML tracker: {file_path}: the top-level "
            "package has no name."
        )
    return package.name


def _sysml_files(directory: str) -> List[str]:
    result: List[str] = []
    for current_directory_, directories_, files_ in os.walk(directory):
        directories_[:] = sorted(
            directory_
            for directory_ in directories_
            if not directory_.startswith((".", "_"))
        )
        for file_ in sorted(files_):
            if file_.endswith(".sysml"):
                result.append(os.path.join(current_directory_, file_))
    return result


def _included_id(target: str) -> Optional[str]:
    match = _INCLUDE_PATTERN.match(target)
    if match is None:
        return None
    return unquote_name(match.group(1))


def _import_text(member: SysMLImport) -> str:
    if member.visibility is not None:
        return f"{member.visibility} import {member.target};"
    return f"import {member.target};"


def _title(package: SysMLPackage, metadata_name: str, default: str) -> str:
    title = metadata_value(package, metadata_name, "title")
    if title is not None and len(title) > 0:
        return title
    return default


def _first_doc(package: SysMLPackage) -> Optional[SysMLDocComment]:
    for member_ in package.members:
        if isinstance(member_, SysMLDocComment):
            return member_
    return None


def _as_members(
    children: List[Union[TrackerFolder, TrackerItem]],
) -> List[SysMLMember]:
    members: List[SysMLMember] = []
    for child_ in children:
        if isinstance(child_, TrackerFolder):
            folder_members: List[SysMLMember] = []
            if child_.doc is not None:
                folder_members.append(child_.doc)
            folder_members.extend(_as_members(child_.children))
            members.append(
                SysMLPackage(
                    name=child_.title,
                    short_name=None,
                    members=folder_members,
                    span=child_.package.span,
                )
            )
        else:
            members.extend(child_.content_members())
    return members


def _map_member(
    member: SysMLMember, item: TrackerItem, result: Dict[int, TrackerItem]
) -> None:
    result[id(member)] = item
    nested_members = getattr(member, "members", None)
    if isinstance(nested_members, list):
        for nested_member_ in nested_members:
            _map_member(nested_member_, item, result)


def _collect_items(
    children: List[Union[TrackerFolder, TrackerItem]],
    result: List[TrackerItem],
) -> None:
    for child_ in children:
        if isinstance(child_, TrackerFolder):
            _collect_items(child_.children, result)
        else:
            result.append(child_)


def _collect_folders(
    children: List[Union[TrackerFolder, TrackerItem]],
    result: List[TrackerFolder],
) -> None:
    for child_ in children:
        if isinstance(child_, TrackerFolder):
            result.append(child_)
            _collect_folders(child_.children, result)
