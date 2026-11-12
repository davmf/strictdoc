"""
Saved views of the SysML workspace: SysML `view` items that PlantUML draws
with `diagram=<ID>` (see docs/SYSML_WORKSPACE.md of the PlantUML fork).

    package 'BEH-006' {
        private import 'TRK-BEH'::*;

        view <'BEH-006'> 'Heating only' {
            doc /*
             * The heating state, primary transitions only.
             */
            @StrictDocWorkspace::DiagramView {
                options = "transitions=primary";
                plantuml = "note right of ramp : reviewed";
            }
            expose 'BEH-001'::top::heating::**;
        }
    }

- read_view() gives the fields of the view editor from a view file.
- view_text() writes a view file from those fields. The preview of the
  editor draws this text before it is saved.
- create_view() saves a view of any entry with a diagram ("Save as view").
- save_view() writes the edited fields back.
- expose_suggestions() lists what a view can expose: the trackers, folders
  and items, and the states of state machines (`'BEH-001'::top::heating`).
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from strictdoc.backend.sysml.model import (
    SysMLDocComment,
    SysMLElement,
    SysMLImport,
    SysMLMember,
    SysMLMetadataUsage,
    SysMLOpaque,
)
from strictdoc.backend.sysml.parser import SysMLParser
from strictdoc.features.sysml_workspace.templates import (
    INDENT,
    REQUIREMENTS_KIND,
    WorkspaceEditError,
    checked_title,
    new_item_id,
    new_path,
    quote_name,
    write_and_include,
)
from strictdoc.features.sysml_workspace.workspace import (
    ENTRY_FOLDER,
    ENTRY_ITEM,
    ENTRY_TRACKER,
    Workspace,
    WorkspaceEntry,
)
from strictdoc.helpers.file_system import file_open_read_utf8

DIAGRAM_VIEW_METADATA = "StrictDocWorkspace::DiagramView"
# The node types whose trace diagram is a requirements view focused on them.
REQUIREMENT_NODE_TYPES = ("REQUIREMENT", "VERIFICATION", "VERIFICATION_DEF")
# Nested parts of a profile root offered as expose paths, at most.
MAX_SUGGESTED_PATHS = 200
MAX_PATH_DEPTH = 6

# An expose target: names and `::`, quoted names, `*` and `**`. No `;`,
# braces or comments, which would end the statement or the view.
_EXPOSE_PATTERN = re.compile(r"^(?:'(?:[^'\\\n]|\\.)*'|[A-Za-z0-9_*:.\s-])+$")


@dataclass
class ViewFields:
    title: str
    description: str = ""
    exposes: List[str] = field(default_factory=list)
    options: str = ""
    plantuml: str = ""
    imports: List[str] = field(default_factory=list)


def read_view(entry: WorkspaceEntry) -> Optional[ViewFields]:
    """The fields of a view item, from its file. None if it holds no view."""
    if entry.file_path is None:
        return None
    with file_open_read_utf8(entry.file_path) as file_:
        text = file_.read()
    model = SysMLParser.parse_string(text, entry.file_path)
    for package_ in model.members:
        members = getattr(package_, "members", [])
        imports = [
            _import_text(member_)
            for member_ in members
            if isinstance(member_, SysMLImport)
        ]
        for member_ in members:
            if isinstance(member_, SysMLElement) and member_.kind == "view":
                return _view_fields(member_, imports)
    return None


def view_text(view_id: str, fields: ViewFields) -> str:
    """The text of the file of a view."""
    lines = [f"package {quote_name(view_id)} {{"]
    lines.extend(f"{INDENT}{import_}" for import_ in fields.imports)
    if len(fields.imports) > 0:
        lines.append("")
    lines.append(
        f"{INDENT}view <{quote_name(view_id)}> {quote_name(fields.title)} {{"
    )
    description = fields.description.strip()
    if len(description) > 0:
        lines.append(f"{INDENT * 2}doc /*")
        for line_ in description.splitlines():
            lines.append(f"{INDENT * 2} * {line_}".rstrip())
        lines.append(f"{INDENT * 2} */")
    lines.append(f"{INDENT * 2}@{DIAGRAM_VIEW_METADATA} {{")
    lines.append(
        f"{INDENT * 3}options = "
        f"{_multiline_string(' '.join(fields.options.split()))};"
    )
    lines.append(
        f"{INDENT * 3}plantuml = {_multiline_string(fields.plantuml)};"
    )
    lines.append(f"{INDENT * 2}}}")
    for expose_ in fields.exposes:
        lines.append(f"{INDENT * 2}expose {expose_};")
    lines.append(f"{INDENT}}}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def checked_view_fields(
    workspace: Workspace,
    view_tracker: WorkspaceEntry,
    title: str,
    description: str,
    exposes: str,
    options: str,
    plantuml: str,
) -> ViewFields:
    """The fields of the view editor, checked, with the imports they need."""
    title = checked_title(title)
    if "*/" in description:
        raise WorkspaceEditError("The description cannot contain '*/'.")
    if "\n" in options or "\r" in options:
        raise WorkspaceEditError(
            'The options are one line of key=value words (key="a b" for a '
            "value with spaces)."
        )
    expose_list = []
    for line_ in exposes.splitlines():
        expose_ = (
            re.sub(r"^\s*expose\s+", "", line_).strip().rstrip(";").strip()
        )
        if len(expose_) == 0:
            continue
        if _EXPOSE_PATTERN.match(expose_) is None:
            raise WorkspaceEditError(
                f"'{expose_}' is not an expose target: an ID, then names "
                "separated by '::' ('BEH-001'::top::heating)."
            )
        expose_list.append(expose_)
    return ViewFields(
        title=title,
        description=description.strip(),
        exposes=expose_list,
        options=options.strip(),
        plantuml=plantuml.replace("\r\n", "\n").strip("\n"),
        imports=_view_imports(workspace, view_tracker, expose_list),
    )


def view_trackers(workspace: Workspace) -> List[WorkspaceEntry]:
    """The trackers that can hold a view: all but requirements trackers."""
    return [
        tracker_
        for tracker_ in workspace.trackers()
        if tracker_.tracker_kind != REQUIREMENTS_KIND
    ]


def default_view_tracker(
    workspace: Workspace, entry: WorkspaceEntry
) -> Optional[WorkspaceEntry]:
    trackers = view_trackers(workspace)
    if entry.tracker is not None and entry.tracker in trackers:
        return entry.tracker
    return trackers[0] if len(trackers) > 0 else None


def initial_view_fields(entry: WorkspaceEntry) -> Optional[ViewFields]:
    """
    A view that draws the diagram of the entry on the workspace screen, or
    None when the entry has no diagram to save.
    """
    if entry.entry_type in (ENTRY_TRACKER, ENTRY_FOLDER):
        tracker_entry = entry.tracker
        is_design = tracker_entry is not None and tracker_entry.is_design()
        return ViewFields(
            title=f"{entry.title} overview",
            exposes=[f"{quote_name(entry.entry_id)}::**"],
            options="view=definitions" if is_design else "depth=1 text=false",
        )
    if entry.entry_type != ENTRY_ITEM or entry.icon == "view":
        return None
    if entry.profile_type is not None:
        return ViewFields(
            title=f"{entry.title} view", exposes=[quote_name(entry.entry_id)]
        )
    if (
        entry.node is not None
        and entry.node.node_type in REQUIREMENT_NODE_TYPES
    ):
        return ViewFields(
            title=f"{entry.title} traces",
            exposes=[quote_name(entry.entry_id)],
            options="depth=1",
        )
    # A design element that no profile draws: its trace diagram. An expose
    # would make it the root of a profile diagram, so the options say it.
    return ViewFields(
        title=f"{entry.title} traces",
        options=f"view=requirements focus={entry.entry_id} depth=1",
    )


def create_view(
    workspace: Workspace, source_id: str, tracker_id: str, title: str
) -> str:
    """Save the diagram of an entry as a new view item. Returns its ID."""
    source = workspace.get(source_id)
    initial = initial_view_fields(source) if source is not None else None
    if source is None or initial is None:
        raise WorkspaceEditError(f"'{source_id}' has no diagram to save.")
    view_tracker = workspace.get(tracker_id)
    if view_tracker is None or view_tracker not in view_trackers(workspace):
        raise WorkspaceEditError(
            f"'{tracker_id}' cannot hold a view: choose a tracker that is "
            "not a requirements tracker."
        )
    fields = checked_view_fields(
        workspace,
        view_tracker,
        title if title.strip() != "" else initial.title,
        "",
        "\n".join(initial.exposes),
        initial.options,
        "",
    )
    view_id = new_item_id(workspace, view_tracker)
    assert view_tracker.file_path is not None
    write_and_include(
        new_path=new_path(view_tracker, view_id),
        text=view_text(view_id, fields),
        parent_path=view_tracker.file_path,
        include_line=f"{INDENT}public import {quote_name(view_id)}::*;",
    )
    return view_id


def save_view(workspace: Workspace, view_id: str, fields: ViewFields) -> str:
    view = workspace.get(view_id)
    if view is None or view.icon != "view" or view.file_path is None:
        raise WorkspaceEditError(f"'{view_id}' is not a view.")
    text = view_text(view_id, fields)
    with open(view.file_path, "w", encoding="utf-8") as file_:
        file_.write(text)
    return view_id


def view_entry(workspace: Workspace, view_id: str) -> WorkspaceEntry:
    view = workspace.get(view_id)
    if view is None or view.icon != "view" or view.tracker is None:
        raise WorkspaceEditError(f"'{view_id}' is not a view.")
    return view


def expose_suggestions(workspace: Workspace) -> List[str]:
    """What a view can expose, in the order of the tree."""
    suggestions: List[str] = []
    for tracker_ in workspace.trackers():
        suggestions.append(f"{quote_name(tracker_.entry_id)}::**")
        _add_suggestions(tracker_, suggestions)
    return suggestions


def _add_suggestions(entry: WorkspaceEntry, suggestions: List[str]) -> None:
    for child_ in entry.children:
        if child_.entry_type == ENTRY_FOLDER:
            suggestions.append(f"{quote_name(child_.entry_id)}::**")
            _add_suggestions(child_, suggestions)
        elif child_.icon != "view":
            suggestions.append(quote_name(child_.entry_id))
            if child_.profile_type is not None:
                suggestions.extend(
                    f"{quote_name(child_.entry_id)}::{path_}"
                    for path_ in _profile_paths(child_)
                )


def _profile_paths(entry: WorkspaceEntry) -> List[str]:
    """The paths of the parts inside a profile root: `top::heating`."""
    if entry.file_path is None:
        return []
    try:
        with file_open_read_utf8(entry.file_path) as file_:
            model = SysMLParser.parse_string(file_.read(), entry.file_path)
    except Exception:  # noqa: BLE001
        return []
    paths: List[str] = []
    for package_ in model.members:
        for member_ in getattr(package_, "members", []):
            if isinstance(member_, SysMLElement) and member_.kind == "part":
                _collect_paths(member_.members, [], paths)
                return paths
    return paths


def _collect_paths(
    members: Sequence[SysMLMember], prefix: List[str], paths: List[str]
) -> None:
    for member_ in members:
        if len(paths) >= MAX_SUGGESTED_PATHS or len(prefix) >= MAX_PATH_DEPTH:
            return
        if not isinstance(member_, SysMLElement) or member_.kind != "part":
            continue
        name = (
            member_.name
            if member_.name is not None
            else (member_.redefines[0] if len(member_.redefines) > 0 else None)
        )
        if name is None:
            continue
        path = [*prefix, name if re.match(r"^\w+$", name) else quote_name(name)]
        paths.append("::".join(path))
        _collect_paths(member_.members, path, paths)


def _view_fields(view: SysMLElement, imports: List[str]) -> ViewFields:
    fields = ViewFields(
        title=view.name if view.name is not None else "", imports=imports
    )
    for member_ in view.members:
        if isinstance(member_, SysMLDocComment):
            fields.description = _doc_text(member_.text)
        elif isinstance(member_, SysMLMetadataUsage) and member_.name in (
            DIAGRAM_VIEW_METADATA,
            "DiagramView",
        ):
            fields.options = _string_value(member_.values.get("options"))
            fields.plantuml = _string_value(member_.values.get("plantuml"))
        elif isinstance(member_, SysMLOpaque):
            match_ = re.match(
                r"^\s*expose\s+(.*?)\s*;?\s*$", member_.text, re.DOTALL
            )
            if match_ is not None:
                fields.exposes.append(match_.group(1))
    return fields


def _view_imports(
    workspace: Workspace, view_tracker: WorkspaceEntry, exposes: List[str]
) -> List[str]:
    """The view's own tracker, then the trackers of what it exposes."""
    tracker_ids = [view_tracker.entry_id]
    for expose_ in exposes:
        match_ = re.match(r"^\s*('(?:[^'\\]|\\.)*'|[\w-]+)", expose_)
        if match_ is None:
            continue
        first = match_.group(1)
        if first.startswith("'"):
            first = first[1:-1].replace("\\'", "'")
        exposed = workspace.get(first)
        if exposed is None or exposed.tracker is None:
            continue
        if exposed.tracker.entry_id not in tracker_ids:
            tracker_ids.append(exposed.tracker.entry_id)
    return [
        f"private import {quote_name(tracker_id_)}::*;"
        for tracker_id_ in tracker_ids
    ]


def _import_text(member: SysMLImport) -> str:
    visibility = f"{member.visibility} " if member.visibility else ""
    return f"{visibility}import {member.target};"


def _string_value(raw: Optional[str]) -> str:
    if raw is None:
        return ""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        raw = raw[1:-1]
    # The escapes that PlantUML decodes (SysmlWorkspace.getMetadataValue).
    return raw.replace("\\n", "\n").replace('\\"', '"')


def _multiline_string(text: str) -> str:
    return '"' + text.replace('"', '\\"').replace("\n", "\\n") + '"'


def _doc_text(text: str) -> str:
    lines = [re.sub(r"^\s*\*\s?", "", line_) for line_ in text.splitlines()]
    return "\n".join(lines).strip()
