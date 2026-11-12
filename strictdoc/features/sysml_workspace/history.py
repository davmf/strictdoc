"""
The Git history of a file of the workspace: its commits (`git log
--follow`) and whether it has changes that are not committed.
"""

import os
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

GIT_TIMEOUT_SECONDS = 10
_FIELD_SEPARATOR = "\x1f"
_LOG_FORMAT = _FIELD_SEPARATOR.join(("%H", "%h", "%an", "%as", "%s"))


@dataclass
class Commit:
    commit_hash: str
    short_hash: str
    author: str
    date: str
    subject: str


@dataclass
class FileHistory:
    commits: List[Commit] = field(default_factory=list)
    # "untracked", "modified", "added" or None (no change).
    change: Optional[str] = None
    # Why there is no history: no Git, not in a repository...
    error: Optional[str] = None


def file_history(path: str, limit: int = 30) -> FileHistory:
    directory = os.path.dirname(os.path.abspath(path))
    name = os.path.basename(path)
    status = _git(directory, ["status", "--porcelain", "--", name])
    if status.error is not None:
        return FileHistory(error=status.error)
    history = FileHistory(change=_change(status.output))
    log = _git(
        directory,
        [
            "log",
            "--follow",
            f"--max-count={limit}",
            f"--format={_LOG_FORMAT}",
            "--",
            name,
        ],
    )
    if log.error is not None:
        history.error = log.error
        return history
    for line_ in log.output.splitlines():
        parts = line_.split(_FIELD_SEPARATOR)
        if len(parts) == 5:
            history.commits.append(Commit(*parts))
    return history


@dataclass
class _GitResult:
    output: str = ""
    error: Optional[str] = None


def _git(directory: str, arguments: List[str]) -> _GitResult:
    try:
        completed = subprocess.run(
            ["git", "-C", directory, *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return _GitResult(error="Git is not installed.")
    except subprocess.TimeoutExpired:
        return _GitResult(error="Git did not answer in time.")
    if completed.returncode != 0:
        message = completed.stderr.strip().splitlines()
        return _GitResult(
            error=message[-1] if len(message) > 0 else "Git failed."
        )
    return _GitResult(output=completed.stdout)


def _change(status_output: str) -> Optional[str]:
    for line_ in status_output.splitlines():
        code = line_[:2]
        if code == "??":
            return "untracked"
        if "A" in code:
            return "added"
        if code.strip() != "":
            return "modified"
    return None
