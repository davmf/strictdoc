"""
The model of the SysML workspace screen, read from the SysML files.

The model root is the file with `@StrictDocWorkspace::Model` metadata. It
includes the trackers (`public import 'TRK-X';`), in the order of the tree.
A tracker that the model root does not include comes after the included
ones. Each tracker is read with tracker.read_tracker() (its folders and
items) and with SysMLReader.read_from_tracker_file() (the nodes of the
items: fields and relations).

WorkspaceCache keeps the model until a .sysml file of the project changes,
is added or is removed.
"""

import os
import re
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Union

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sdoc.models.reference import (
    ChildReqReference,
    ParentReqReference,
)
from strictdoc.backend.sysml import node_data, tracker
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.sysml_diagrams.model_files import (
    ModelFile,
    find_model_file_paths,
)
from strictdoc.helpers.file_system import file_open_read_utf8

MODEL_METADATA = "Model"
_MODEL_PATTERN = re.compile(
    r"@\s*(?:'?StrictDocWorkspace'?\s*::\s*)?'?Model'?\s*\{"
)
# `public import 'TRK-X';` in the model root.
_MODEL_INCLUDE_PATTERN = re.compile(
    r"^\s*public\s+import\s+('(?:[^'\\]|\\.)*'|[A-Za-z_][A-Za-z0-9_-]*)"
    r"\s*;",
    re.MULTILINE,
)
_TITLE_PATTERN = re.compile(r'\btitle\s*=\s*"((?:[^"\\]|\\.)*)"')

ENTRY_MODEL = "model"
ENTRY_TRACKER = "tracker"
ENTRY_FOLDER = "folder"
ENTRY_ITEM = "item"

# The type that makes an element the root of a SysML profile diagram:
# (icon, label).
PROFILE_KINDS: Dict[str, Tuple[str, str]] = {
    "StateMachine": ("statemachine", "State machine"),
    "Interaction": ("sequence", "Sequence"),
    "TimingDiagram": ("timing", "Timing diagram"),
    "Activity": ("activity", "Activity"),
    "InterconnectSystem": ("interconnect", "Interconnect"),
    "PCBA": ("pcba", "PCBA"),
    "COTSDevice": ("cots", "COTS device"),
}

# Node type -> (icon, label).
NODE_KINDS: Dict[str, Tuple[str, str]] = {
    "REQUIREMENT": ("requirement", "Requirement"),
    "VERIFICATION": ("testcase", "Test case"),
    "VERIFICATION_DEF": ("testcase", "Test case definition"),
    "PART": ("part", "Part"),
    "PART_DEF": ("partdef", "Part definition"),
    "ACTION": ("action", "Action"),
    "ACTION_DEF": ("action", "Action definition"),
    "CALC_DEF": ("calc", "Calculation"),
    "ANALYSIS": ("analysis", "Analysis"),
    "ANALYSIS_DEF": ("analysis", "Analysis definition"),
    "VIEW": ("view", "View"),
}

# The fields shown in the header of an item, not in its field list.
HEADER_FIELDS = ("UID", "TITLE", "ELEMENT_KIND", "SOURCE", "MID")


@dataclass
class WorkspaceRelation:
    role: str
    entry: "WorkspaceEntry"


@dataclass
class WorkspaceEntry:
    entry_id: str
    entry_type: str
    title: str
    icon: str
    kind_label: str
    # The absolute path of the file of the entry, and the same path
    # relative to its input path (None for a model root without a file).
    file_path: Optional[str] = None
    relative_path: Optional[str] = None
    parent: Optional["WorkspaceEntry"] = None
    children: List["WorkspaceEntry"] = field(default_factory=list)
    # The node of an item, the section of a folder.
    node: Optional[SDocNode] = None
    # The tracker of a tracker, folder or item entry.
    tracker: Optional["WorkspaceEntry"] = None
    # Trackers only.
    tracker_kind: Optional[str] = None
    prefix: Optional[str] = None
    document: Optional[SDocDocument] = None
    # Trackers only: the URL of the document screen of the tracker.
    document_url: Optional[str] = None
    # Profile diagram roots only: the profile type (StateMachine...).
    profile_type: Optional[str] = None
    outgoing: List[WorkspaceRelation] = field(default_factory=list)
    incoming: List[WorkspaceRelation] = field(default_factory=list)

    def is_design(self) -> bool:
        return self.document is not None and self.document.autogen

    def ancestors(self) -> List["WorkspaceEntry"]:
        result: List[WorkspaceEntry] = []
        parent_ = self.parent
        while parent_ is not None:
            result.insert(0, parent_)
            parent_ = parent_.parent
        return result

    def items(self) -> List["WorkspaceEntry"]:
        """The items below the entry, at any depth."""
        result: List[WorkspaceEntry] = []
        for child_ in self.children:
            if child_.entry_type == ENTRY_ITEM:
                result.append(child_)
            result.extend(child_.items())
        return result

    def fields(self) -> List[Tuple[str, str]]:
        """(field name, text) of the fields of the node of the entry."""
        if self.node is None:
            return []
        result: List[Tuple[str, str]] = []
        for name_, fields_ in self.node.ordered_fields_lookup.items():
            if name_ in HEADER_FIELDS or len(fields_) == 0:
                continue
            result.append((name_, fields_[0].get_text_value()))
        return result


@dataclass
class Workspace:
    root: WorkspaceEntry
    entries: Dict[str, WorkspaceEntry]
    # The messages of the trackers that could not be read.
    errors: List[str]
    # The directory that holds the model root, where new trackers go.
    model_directory: Optional[str]

    def get(self, entry_id: Optional[str]) -> Optional[WorkspaceEntry]:
        if entry_id is None:
            return None
        return self.entries.get(entry_id)

    def trackers(self) -> List[WorkspaceEntry]:
        return [
            child_
            for child_ in self.root.children
            if child_.entry_type == ENTRY_TRACKER
        ]


def build_workspace(
    project_config: ProjectConfig,
    model_files: Sequence[ModelFile],
) -> Workspace:
    """Read the workspace from the .sysml files of the project."""
    files_by_path: Dict[str, ModelFile] = {
        model_file_.full_path: model_file_ for model_file_ in model_files
    }
    relative_paths: Dict[str, str] = {
        model_file_.full_path: model_file_.name for model_file_ in model_files
    }
    model_path: Optional[str] = None
    model_text: str = ""
    tracker_paths: Dict[str, str] = {}
    for model_file_ in model_files:
        full_path_ = model_file_.full_path
        with file_open_read_utf8(full_path_) as file_:
            text_ = file_.read()
        if model_path is None and _MODEL_PATTERN.search(text_) is not None:
            model_path, model_text = full_path_, text_
        elif tracker.is_tracker_file(full_path_):
            file_id = os.path.splitext(os.path.basename(full_path_))[0]
            tracker_paths.setdefault(file_id, full_path_)

    title_match = _TITLE_PATTERN.search(model_text)
    root = WorkspaceEntry(
        entry_id=(
            os.path.splitext(os.path.basename(model_path))[0]
            if model_path is not None
            else "MODEL"
        ),
        entry_type=ENTRY_MODEL,
        title=(
            title_match.group(1)
            if title_match is not None
            else project_config.project_title
        ),
        icon="model",
        kind_label="Model",
        file_path=model_path,
        relative_path=(
            relative_paths.get(model_path) if model_path is not None else None
        ),
    )
    entries: Dict[str, WorkspaceEntry] = {root.entry_id: root}
    errors: List[str] = []

    included = [
        tracker.unquote_name(match_.group(1))
        for match_ in _MODEL_INCLUDE_PATTERN.finditer(model_text)
    ]
    ordered_ids = [id_ for id_ in included if id_ in tracker_paths] + sorted(
        id_ for id_ in tracker_paths if id_ not in included
    )
    for tracker_id_ in ordered_ids:
        tracker_path = tracker_paths[tracker_id_]
        try:
            tracker_entry = _read_tracker(
                tracker_path,
                relative_paths,
                static_directory=project_config.dir_for_sdoc_assets,
            )
        except tracker.TrackerError as tracker_error:
            errors.append(tracker_error.to_print_message())
            continue
        except Exception as read_error:  # noqa: BLE001
            errors.append(f"{relative_paths[tracker_path]}: {read_error}")
            continue
        tracker_entry.parent = root
        tracker_entry.document_url = files_by_path[tracker_path].document_url()
        root.children.append(tracker_entry)
        _index(tracker_entry, entries)

    _link_relations(entries)
    return Workspace(
        root=root,
        entries=entries,
        errors=errors,
        model_directory=(
            os.path.dirname(model_path) if model_path is not None else None
        ),
    )


def _read_tracker(
    tracker_path: str,
    relative_paths: Dict[str, str],
    static_directory: str,
) -> WorkspaceEntry:
    tracker_ = tracker.read_tracker(tracker_path)
    document = SysMLReader.read_from_tracker_file(
        tracker_path,
        relative_path=relative_paths.get(tracker_path, tracker_path),
        static_directory=static_directory,
    )
    item_nodes: Dict[str, SDocNode] = {}
    folder_nodes: Dict[str, SDocNode] = {}
    for node_ in document.iterate_nodes():
        if not isinstance(node_, SDocNode):
            continue
        folder_ = node_data.get_folder(node_)
        if folder_ is not None:
            folder_nodes[folder_.file_id] = node_
        item_file = node_data.get_item_file(node_)
        if item_file is not None and item_file.file_id not in item_nodes:
            item_nodes[item_file.file_id] = node_

    tracker_entry = WorkspaceEntry(
        entry_id=tracker_.tracker_id,
        entry_type=ENTRY_TRACKER,
        title=tracker_.title,
        icon="tracker",
        kind_label=(
            f"Tracker ({tracker_.kind})"
            if tracker_.kind is not None
            else "Tracker"
        ),
        file_path=tracker_.file_path,
        relative_path=relative_paths.get(tracker_.file_path),
        tracker_kind=tracker_.kind,
        prefix=tracker_.prefix,
        document=document,
    )
    tracker_entry.tracker = tracker_entry
    _add_children(
        tracker_entry,
        tracker_.children,
        relative_paths,
        item_nodes,
        folder_nodes,
    )
    return tracker_entry


def _add_children(
    parent: WorkspaceEntry,
    children: Sequence[Union[tracker.TrackerFolder, tracker.TrackerItem]],
    relative_paths: Dict[str, str],
    item_nodes: Dict[str, SDocNode],
    folder_nodes: Dict[str, SDocNode],
) -> None:
    for child_ in children:
        entry: WorkspaceEntry
        if isinstance(child_, tracker.TrackerFolder):
            entry = WorkspaceEntry(
                entry_id=child_.folder_id,
                entry_type=ENTRY_FOLDER,
                title=child_.title,
                icon="folder",
                kind_label="Folder",
                file_path=child_.file_path,
                relative_path=relative_paths.get(child_.file_path),
                parent=parent,
                node=folder_nodes.get(child_.folder_id),
                tracker=parent.tracker,
            )
            _add_children(
                entry,
                child_.children,
                relative_paths,
                item_nodes,
                folder_nodes,
            )
        else:
            node = item_nodes.get(child_.item_id)
            icon, kind_label, profile_type = _item_kind(node)
            entry = WorkspaceEntry(
                entry_id=child_.item_id,
                entry_type=ENTRY_ITEM,
                title=_node_title(node, child_.item_id),
                icon=icon,
                kind_label=kind_label,
                file_path=child_.file_path,
                relative_path=relative_paths.get(child_.file_path),
                parent=parent,
                node=node,
                tracker=parent.tracker,
                profile_type=profile_type,
            )
        parent.children.append(entry)


def _item_kind(
    node: Optional[SDocNode],
) -> Tuple[str, str, Optional[str]]:
    if node is None:
        return "element", "Element", None
    for type_ in node_data.get_type_lineage(node):
        if type_ in PROFILE_KINDS:
            icon, label = PROFILE_KINDS[type_]
            return icon, label, type_
    if node.node_type in NODE_KINDS:
        icon, label = NODE_KINDS[node.node_type]
        return icon, label, None
    return "element", node.node_type.replace("_", " ").capitalize(), None


def _node_title(node: Optional[SDocNode], default: str) -> str:
    if node is None:
        return default
    title_fields = node.ordered_fields_lookup.get("TITLE")
    if title_fields is None or len(title_fields) == 0:
        return default
    return title_fields[0].get_text_value()


def _index(entry: WorkspaceEntry, entries: Dict[str, WorkspaceEntry]) -> None:
    entries.setdefault(entry.entry_id, entry)
    for child_ in entry.children:
        _index(child_, entries)


def _link_relations(entries: Dict[str, WorkspaceEntry]) -> None:
    """
    The relations between items: those of the item node and of the nodes
    of its members (a satisfy statement of a part of the item...). A
    relation to something that is not an entry (a library type) is left
    out.
    """
    # A typing or a specialisation names a design element by its name, not
    # by its item ID.
    names: Dict[str, Optional[WorkspaceEntry]] = {}
    for entry_ in entries.values():
        if (
            entry_.entry_type == ENTRY_ITEM
            and entry_.tracker is not None
            and entry_.tracker.is_design()
        ):
            names[entry_.title] = None if entry_.title in names else entry_
    seen = set()
    for tracker_ in entries.values():
        if tracker_.entry_type != ENTRY_TRACKER or tracker_.document is None:
            continue
        for node_ in tracker_.document.iterate_nodes():
            if not isinstance(node_, SDocNode):
                continue
            item_file = node_data.get_item_file(node_)
            if item_file is None:
                continue
            source = entries.get(item_file.file_id)
            if source is None:
                continue
            for relation_ in node_.relations:
                if not isinstance(
                    relation_, (ParentReqReference, ChildReqReference)
                ):
                    continue
                target = (
                    entries.get(relation_.ref_uid)
                    or names.get(relation_.ref_uid)
                    or names.get(relation_.ref_uid.split("::")[-1])
                )
                if target is None or target is source:
                    continue
                role = (
                    relation_.role if relation_.role is not None else "Parent"
                )
                key = (source.entry_id, role, target.entry_id)
                if key in seen:
                    continue
                seen.add(key)
                source.outgoing.append(WorkspaceRelation(role, target))
                target.incoming.append(WorkspaceRelation(role, source))


class WorkspaceCache:
    """
    The workspace of a project, read again when a .sysml file of the
    project changes, or when a file is added to or removed from a folder
    that holds .sysml files. Scanning the input paths for .sysml files
    takes a while on a large project, so a scan happens only then, or after
    invalidate().
    """

    def __init__(self, project_config: ProjectConfig) -> None:
        self.project_config: ProjectConfig = project_config
        self._lock = threading.Lock()
        self._model_files: Optional[List[ModelFile]] = None
        self._signature: Optional[Tuple[Tuple[str, int, int], ...]] = None
        self._workspace: Optional[Workspace] = None

    def invalidate(self) -> None:
        with self._lock:
            self._model_files = None

    def get(self) -> Workspace:
        with self._lock:
            if (
                self._model_files is None
                or self._workspace is None
                or _signature(self._model_files) != self._signature
            ):
                model_files = find_model_file_paths(self.project_config)
                signature = _signature(model_files)
                if self._workspace is None or signature != self._signature:
                    self._workspace = build_workspace(
                        self.project_config, model_files
                    )
                self._model_files = model_files
                self._signature = signature
            return self._workspace


def _signature(
    model_files: Sequence[ModelFile],
) -> Tuple[Tuple[str, int, int], ...]:
    paths = [model_file_.full_path for model_file_ in model_files]
    directories = sorted({os.path.dirname(path_) for path_ in paths})
    return tuple(_file_signature(path_) for path_ in paths + directories)


def _file_signature(path: str) -> Tuple[str, int, int]:
    try:
        stat = os.stat(path)
    except OSError:
        return (path, -1, -1)
    return (path, stat.st_mtime_ns, stat.st_size)
