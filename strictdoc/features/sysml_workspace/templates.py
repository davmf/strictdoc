"""
New trackers, folders and items of the workspace screen.

An item is created from the template of its kind: a requirement, a test
case, a part, a state machine, a sequence, a timing diagram... The new file
is written next to the tracker file, and its parent (a tracker or a folder)
includes it with `public import '<ID>'::*;`. A new tracker gets a folder of
its own next to the other trackers, and the model root includes it with
`public import 'TRK-<PREFIX>';`.

Nothing is committed: the files are left for a later commit.
"""

import os
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from strictdoc.backend.sysml import node_data
from strictdoc.features.sysml_workspace.workspace import (
    ENTRY_FOLDER,
    ENTRY_TRACKER,
    Workspace,
    WorkspaceEntry,
)
from strictdoc.helpers.file_system import file_open_read_utf8

INDENT = "    "
REQUIREMENTS_KIND = "requirements"
TRACKER_KINDS = ("requirements", "design", "behaviour", "test cases")

_PREFIX_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PUBLIC_IMPORT_PATTERN = re.compile(r"^\s*public\s+import\s")


class WorkspaceEditError(Exception):
    pass


@dataclass(frozen=True)
class ItemTemplate:
    key: str
    label: str
    icon: str
    # Offered in requirements trackers (True) or in the other trackers.
    for_requirements: bool
    # Imports the element needs, besides those of the tracker's items.
    imports: Tuple[str, ...]
    # (item ID, title) -> the lines of the element, without indentation.
    element: Callable[[str, str], List[str]]


def _requirement(item_id: str, title: str) -> List[str]:
    return [
        f"requirement <{quote_name(item_id)}> {quote_name(title)} {{",
        "}",
    ]


def _empty(keyword: str) -> Callable[[str, str], List[str]]:
    def element(_item_id: str, title: str) -> List[str]:
        return [f"{keyword} {_name(title)} {{", "}"]

    return element


def _state_machine(_item_id: str, title: str) -> List[str]:
    return [
        f"part {_name(title)} : StateMachine {{",
        f"{INDENT}:>> name = {sysml_string(title)};",
        "",
        f"{INDENT}part :>> top : Region {{",
        (
            f"{INDENT * 2}part init : Pseudostate "
            "{ :>> kind = PseudostateKind::initial; }"
        ),
        f'{INDENT * 2}part idle : State {{ :>> name = "Idle"; }}',
        (
            f"{INDENT * 2}connection initToIdle : Transition "
            "connect init.outgoing to idle.incoming {"
        ),
        f"{INDENT * 3}:>> classification = TransitionClassification::primary;",
        f"{INDENT * 2}}}",
        f"{INDENT}}}",
        "}",
    ]


def _sequence(_item_id: str, title: str) -> List[str]:
    name = _name(title)
    return [
        f"part {name} : Interaction {{",
        f"{INDENT}:>> name = {sysml_string(title)};",
        "",
        f"{INDENT}part :>> participantClasses {{",
        (
            f"{INDENT * 2}part userClass : ParticipantClass "
            '{ :>> name = "User"; }'
        ),
        (
            f"{INDENT * 2}part systemClass : ParticipantClass "
            '{ :>> name = "System"; }'
        ),
        f"{INDENT}}}",
        "",
        f"{INDENT}part :>> lifelines {{",
        f"{INDENT * 2}part user : Lifeline {{",
        f'{INDENT * 3}:>> name = "user";',
        f"{INDENT * 3}:>> kind = InteractionParticipantKind::actorParticipant;",
        f"{INDENT * 3}:>> represents = {name}.participantClasses.userClass;",
        f"{INDENT * 2}}}",
        f"{INDENT * 2}part system : Lifeline {{",
        f'{INDENT * 3}:>> name = "system";',
        f"{INDENT * 3}:>> kind = InteractionParticipantKind::lifeline;",
        f"{INDENT * 3}:>> represents = {name}.participantClasses.systemClass;",
        f"{INDENT * 2}}}",
        f"{INDENT}}}",
        "",
        f"{INDENT}part :>> messages {{",
        f"{INDENT * 2}part request : Message {{",
        f'{INDENT * 3}:>> name = "request()";',
        f"{INDENT * 3}:>> kind = MessageKind::synchronous;",
        f'{INDENT * 3}:>> signature = "request()";',
        f"{INDENT * 3}:>> order = 1;",
        f"{INDENT * 3}connect source to {name}.lifelines.user.outgoing;",
        f"{INDENT * 3}connect target to {name}.lifelines.system.incoming;",
        f"{INDENT * 2}}}",
        f"{INDENT}}}",
        "}",
    ]


def _timing(_item_id: str, title: str) -> List[str]:
    return [
        f"part {_name(title)} : TimingDiagram {{",
        f"{INDENT}:>> name = {sysml_string(title)};",
        f"{INDENT}:>> timeUnit = TimeUnit::us;",
        "",
        f"{INDENT}part :>> lifelines {{",
        f"{INDENT * 2}part clock : Lifeline {{",
        f'{INDENT * 3}:>> name = "Clock";',
        f"{INDENT * 3}:>> kind = LifelineKind::clock;",
        f"{INDENT * 3}:>> periodNs = 1000;",
        f"{INDENT * 2}}}",
        f"{INDENT * 2}part state : Lifeline {{",
        f'{INDENT * 3}:>> name = "State";',
        f"{INDENT * 3}:>> kind = LifelineKind::robust;",
        "",
        f"{INDENT * 3}part :>> changes {{",
        (
            f"{INDENT * 4}part idle : StateChange "
            '{ :>> atNs = 0; :>> value = "Idle"; }'
        ),
        (
            f"{INDENT * 4}part busy : StateChange "
            '{ :>> atNs = 2000; :>> value = "Busy"; }'
        ),
        f"{INDENT * 3}}}",
        f"{INDENT * 2}}}",
        f"{INDENT}}}",
        "}",
    ]


ITEM_TEMPLATES: List[ItemTemplate] = [
    ItemTemplate(
        "requirement", "Requirement", "requirement", True, (), _requirement
    ),
    ItemTemplate(
        "testcase",
        "Test case",
        "testcase",
        False,
        (),
        _empty("verification"),
    ),
    ItemTemplate("part", "Part", "part", False, (), _empty("part")),
    ItemTemplate(
        "partdef",
        "Part definition",
        "partdef",
        False,
        (),
        _empty("part def"),
    ),
    ItemTemplate("action", "Action", "action", False, (), _empty("action")),
    ItemTemplate(
        "statemachine",
        "State machine",
        "statemachine",
        False,
        ("private import StateMachineProfile::*;",),
        _state_machine,
    ),
    ItemTemplate(
        "sequence",
        "Sequence",
        "sequence",
        False,
        ("private import SequenceProfile::*;",),
        _sequence,
    ),
    ItemTemplate(
        "timing",
        "Timing diagram",
        "timing",
        False,
        ("private import TimingProfile::*;",),
        _timing,
    ),
]
ITEM_TEMPLATES_BY_KEY: Dict[str, ItemTemplate] = {
    template_.key: template_ for template_ in ITEM_TEMPLATES
}


def templates_for(entry: WorkspaceEntry) -> List[ItemTemplate]:
    """The templates of the items that a tracker or a folder may hold."""
    tracker_entry = entry.tracker
    if tracker_entry is None:
        return []
    is_requirements = tracker_entry.tracker_kind == REQUIREMENTS_KIND
    return [
        template_
        for template_ in ITEM_TEMPLATES
        if template_.for_requirements == is_requirements
    ]


def create_item(
    workspace: Workspace, parent_id: str, template_key: str, title: str
) -> str:
    """Write a new item file and include it. Returns the ID of the item."""
    parent = _container(workspace, parent_id)
    template = ITEM_TEMPLATES_BY_KEY.get(template_key)
    if template is None or template not in templates_for(parent):
        raise WorkspaceEditError(
            f"A {parent.kind_label.lower()} of this tracker cannot hold "
            f"an item of the kind '{template_key}'."
        )
    title = checked_title(title)
    tracker_entry = parent.tracker
    assert tracker_entry is not None and tracker_entry.file_path is not None
    item_id = new_item_id(workspace, tracker_entry)
    imports = _item_imports(tracker_entry)
    for import_ in template.imports:
        if import_ not in imports:
            imports.append(import_)
    lines = [f"package {quote_name(item_id)} {{"]
    lines.extend(f"{INDENT}{import_}" for import_ in imports)
    lines.append("")
    lines.extend(
        f"{INDENT}{line_}" if len(line_) > 0 else ""
        for line_ in template.element(item_id, title)
    )
    lines.append("}")
    write_and_include(
        new_path=new_path(tracker_entry, item_id),
        text="\n".join(lines) + "\n",
        parent_path=_file_path(parent),
        include_line=f"{INDENT}public import {quote_name(item_id)}::*;",
    )
    return item_id


def create_folder(workspace: Workspace, parent_id: str, title: str) -> str:
    """Write a new folder file and include it. Returns its ID."""
    parent = _container(workspace, parent_id)
    title = checked_title(title)
    tracker_entry = parent.tracker
    assert tracker_entry is not None
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").upper()
    base_id = f"{tracker_prefix(tracker_entry)}-F-{slug if len(slug) > 0 else 'FOLDER'}"
    folder_id = base_id
    counter = 2
    while folder_id in workspace.entries or os.path.exists(
        new_path(tracker_entry, folder_id, check=False)
    ):
        folder_id = f"{base_id}-{counter}"
        counter += 1
    text = (
        f"package {quote_name(folder_id)} {{\n"
        f"{INDENT}@StrictDocWorkspace::Folder {{ title = {sysml_string(title)}; }}\n"
        "}\n"
    )
    write_and_include(
        new_path=new_path(tracker_entry, folder_id),
        text=text,
        parent_path=_file_path(parent),
        include_line=f"{INDENT}public import {quote_name(folder_id)}::*;",
    )
    return folder_id


def create_tracker(
    workspace: Workspace, title: str, kind: str, prefix: str
) -> str:
    """
    Write a new tracker file, in a folder of its own next to the other
    trackers, and include it in the model root. Returns its ID.
    """
    root = workspace.root
    if root.file_path is None or workspace.model_directory is None:
        raise WorkspaceEditError(
            "The model has no root file (a package with "
            "@StrictDocWorkspace::Model metadata) to include the tracker."
        )
    title = checked_title(title)
    if kind not in TRACKER_KINDS:
        raise WorkspaceEditError(
            f"Unknown tracker kind '{kind}': expected one of "
            + ", ".join(TRACKER_KINDS)
            + "."
        )
    prefix = prefix.strip()
    if _PREFIX_PATTERN.match(prefix) is None:
        raise WorkspaceEditError(
            "A prefix is upper-case letters and digits, starting with a "
            "letter (SYS, HW2...)."
        )
    for tracker_ in workspace.trackers():
        if tracker_prefix(tracker_) == prefix:
            raise WorkspaceEditError(
                f"The tracker {tracker_.entry_id} already uses the prefix "
                f"'{prefix}'."
            )
    tracker_id = f"TRK-{prefix}"
    directory = os.path.join(workspace.model_directory, tracker_id)
    if tracker_id in workspace.entries or os.path.exists(directory):
        raise WorkspaceEditError(f"{directory} exists already.")
    text = (
        f"package {quote_name(tracker_id)} {{\n"
        f"{INDENT}@StrictDocWorkspace::Tracker {{ title = {sysml_string(title)}; "
        f"kind = {sysml_string(kind)}; prefix = {sysml_string(prefix)}; }}\n"
        "}\n"
    )
    os.makedirs(directory)
    try:
        write_and_include(
            new_path=os.path.join(directory, f"{tracker_id}.sysml"),
            text=text,
            parent_path=root.file_path,
            include_line=f"{INDENT}public import {quote_name(tracker_id)};",
        )
    except Exception:
        os.rmdir(directory)
        raise
    return tracker_id


def _container(workspace: Workspace, parent_id: str) -> WorkspaceEntry:
    parent = workspace.get(parent_id)
    if parent is None or parent.entry_type not in (
        ENTRY_TRACKER,
        ENTRY_FOLDER,
    ):
        raise WorkspaceEditError(
            f"'{parent_id}' is not a tracker or a folder of the workspace."
        )
    return parent


def checked_title(title: str) -> str:
    title = title.strip()
    if len(title) == 0:
        raise WorkspaceEditError("The title is empty.")
    if "\n" in title or "\r" in title:
        raise WorkspaceEditError("The title is one line.")
    return title


def tracker_prefix(tracker_entry: WorkspaceEntry) -> str:
    if tracker_entry.prefix is not None and len(tracker_entry.prefix) > 0:
        return tracker_entry.prefix
    return re.sub(r"^TRK-", "", tracker_entry.entry_id)


def new_item_id(workspace: Workspace, tracker_entry: WorkspaceEntry) -> str:
    prefix = tracker_prefix(tracker_entry)
    pattern = re.compile(re.escape(prefix) + r"-(\d+)$")
    highest = 0
    for id_ in workspace.entries:
        match_ = pattern.match(id_)
        if match_ is not None:
            highest = max(highest, int(match_.group(1)))
    number = highest + 1
    while True:
        item_id = f"{prefix}-{number:03d}"
        if item_id not in workspace.entries and not os.path.exists(
            new_path(tracker_entry, item_id, check=False)
        ):
            return item_id
        number += 1


def _item_imports(tracker_entry: WorkspaceEntry) -> List[str]:
    """The imports of the first item of the tracker, as the writer does."""
    for item_ in tracker_entry.items():
        if item_.node is not None:
            imports = node_data.get_imports(item_.node)
            if len(imports) > 0:
                return list(imports)
    return [f"private import {quote_name(tracker_entry.entry_id)}::*;"]


def new_path(
    tracker_entry: WorkspaceEntry, file_id: str, check: bool = True
) -> str:
    assert tracker_entry.file_path is not None
    path = os.path.join(
        os.path.dirname(tracker_entry.file_path), f"{file_id}.sysml"
    )
    if check and os.path.exists(path):
        raise WorkspaceEditError(f"{path} exists already.")
    return path


def _file_path(entry: WorkspaceEntry) -> str:
    if entry.file_path is None:
        raise WorkspaceEditError(f"'{entry.entry_id}' has no file.")
    return entry.file_path


def write_and_include(
    *, new_path: str, text: str, parent_path: str, include_line: str
) -> None:
    with open(new_path, "x", encoding="utf-8") as file_:
        file_.write(text)
    try:
        add_include(parent_path, include_line)
    except Exception:
        os.remove(new_path)
        raise


def add_include(path: str, include_line: str) -> None:
    """
    Add an include to the top-level package of a file: after its last
    `public import`, or else before its closing brace.
    """
    with file_open_read_utf8(path) as file_:
        text = file_.read()
    lines = text.splitlines()
    index: Optional[int] = None
    for index_, line_ in enumerate(lines):
        if _PUBLIC_IMPORT_PATTERN.match(line_) is not None:
            index = index_ + 1
    if index is None:
        closing = [
            index_ for index_, line_ in enumerate(lines) if line_.strip() == "}"
        ]
        if len(closing) == 0:
            raise WorkspaceEditError(
                f"{path}: cannot find the end of the top-level package."
            )
        index = closing[-1]
        previous = lines[index - 1].strip() if index > 0 else ""
        if previous not in ("", "{") and not previous.endswith("{"):
            lines.insert(index, "")
            index += 1
    lines.insert(index, include_line)
    with open(path, "w", encoding="utf-8") as file_:
        file_.write("\n".join(lines) + "\n")


def quote_name(name: str) -> str:
    return "'" + name.replace("\\", "\\\\").replace("'", "\\'") + "'"


def sysml_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _name(title: str) -> str:
    """
    The name of a design element: its title, quoted unless it is an
    identifier (`'Pump head'`, `PumpHead`).
    """
    if _IDENTIFIER_PATTERN.match(title) is not None:
        return title
    return quote_name(title)
