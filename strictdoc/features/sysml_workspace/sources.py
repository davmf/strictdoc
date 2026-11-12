"""
The SysML source of a workspace entry: checked as it is typed, saved when
it still reads.

check_source() looks at the text alone: it must parse, and hold one
top-level package named by the ID of the entry (the file name).

save_source() also needs the rest of the model. Under the write lock of the
server, it refuses a file that changed on disk since the editor opened it,
writes the text, and reads the tracker of the entry again. If the tracker
no longer reads (an include that names no file...), the old text goes back
and the save is refused with the message of the reader.
"""

import os
import re
from dataclasses import dataclass
from typing import List, Optional

from strictdoc.backend.sysml import tracker
from strictdoc.backend.sysml.model import SysMLPackage
from strictdoc.backend.sysml.parser import SysMLParseError, SysMLParser
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.features.sysml_workspace.templates import WorkspaceEditError
from strictdoc.features.sysml_workspace.workspace import (
    ENTRY_MODEL,
    Workspace,
    WorkspaceEntry,
)
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.file_system import file_open_read_utf8

_LINE_PATTERN = re.compile(r"line (\d+)(?:, column (\d+))?")


@dataclass
class SourceProblem:
    message: str
    line: Optional[int] = None
    column: Optional[int] = None


def read_source(entry: WorkspaceEntry) -> Optional[str]:
    if entry.file_path is None or not os.path.isfile(entry.file_path):
        return None
    with file_open_read_utf8(entry.file_path) as file_:
        return file_.read()


def source_hash(text: str) -> str:
    return tracker.text_hash(text)


def check_source(entry: WorkspaceEntry, text: str) -> List[SourceProblem]:
    """The problems of the text of an entry's file, without the other files."""
    name = (
        os.path.basename(entry.file_path)
        if entry.file_path is not None
        else entry.entry_id
    )
    try:
        model = SysMLParser.parse_string(text, name)
    except SysMLParseError as parse_error:
        message = parse_error.to_print_message()
        match_ = _LINE_PATTERN.search(message)
        return [
            SourceProblem(
                message=message,
                line=int(match_.group(1)) if match_ is not None else None,
                column=(
                    int(match_.group(2))
                    if match_ is not None and match_.group(2) is not None
                    else None
                ),
            )
        ]
    packages = [
        member_
        for member_ in model.members
        if isinstance(member_, SysMLPackage)
    ]
    if len(model.members) != 1 or len(packages) != 1:
        return [
            SourceProblem(
                f"{name}: the file holds one top-level package, found "
                f"{len(model.members)} top-level elements."
            )
        ]
    package = packages[0]
    package_name = (
        tracker.unquote_name(package.name) if package.name is not None else ""
    )
    if package_name != entry.entry_id:
        return [
            SourceProblem(
                f"{name}: the top-level package is '{package_name}', expected "
                f"'{entry.entry_id}': the package is named by the ID of the "
                "file.",
                line=package.span.line_start,
            )
        ]
    return []


def save_source(
    workspace: Workspace, entry_id: str, text: str, base_hash: str
) -> str:
    """
    Write the text of an entry's file. Returns the ID of the entry. Call it
    under the write lock of the server.
    """
    entry = workspace.get(entry_id)
    if entry is None or entry.file_path is None:
        raise WorkspaceEditError(f"'{entry_id}' has no file to edit.")
    text = text.replace("\r\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    problems = check_source(entry, text)
    if len(problems) > 0:
        raise WorkspaceEditError(problems[0].message)
    old_text = read_source(entry)
    if old_text is None or source_hash(old_text) != base_hash:
        raise WorkspaceEditError(
            "The file changed on disk since the editor opened it. Copy your "
            "text, open the file again and make the change there."
        )
    if old_text == text:
        return entry_id
    _write(entry.file_path, text)
    if entry.entry_type != ENTRY_MODEL and entry.tracker is not None:
        assert entry.tracker.file_path is not None
        try:
            tracker.read_tracker(entry.tracker.file_path)
            SysMLReader.read_from_tracker_file(
                entry.tracker.file_path,
                relative_path=entry.tracker.relative_path
                or entry.tracker.file_path,
            )
        except Exception as read_error:
            _write(entry.file_path, old_text)
            message = (
                read_error.to_print_message()
                if isinstance(read_error, StrictDocException)
                else str(read_error)
            )
            raise WorkspaceEditError(
                "Not saved: with this text, the tracker "
                f"{entry.tracker.entry_id} does not read.\n{message}"
            ) from read_error
    return entry_id


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as file_:
        file_.write(text)
