"""
The Git history of a file of the SysML workspace.
"""

import subprocess

from strictdoc.features.sysml_workspace.history import file_history

GIT_IDENTITY = [
    "-c",
    "user.name=Tester",
    "-c",
    "user.email=tester@example.invalid",
]


def _git(directory, *arguments):
    subprocess.run(
        ["git", *GIT_IDENTITY, "-C", str(directory), *arguments],
        check=True,
        capture_output=True,
    )


def test_01_commits_newest_first_and_uncommitted_changes(tmp_path):
    _git(tmp_path, "init", "-q")
    path = tmp_path / "SYS-001.sysml"
    path.write_text("package 'SYS-001' {}\n", encoding="utf-8")
    assert file_history(str(path)).change == "untracked"
    _git(tmp_path, "add", "SYS-001.sysml")
    _git(tmp_path, "commit", "-q", "-m", "Add SYS-001")
    path.write_text("package 'SYS-001' { }\n", encoding="utf-8")
    _git(tmp_path, "commit", "-q", "-am", "Edit SYS-001")
    history = file_history(str(path))
    assert history.error is None
    assert history.change is None
    assert [commit_.subject for commit_ in history.commits] == [
        "Edit SYS-001",
        "Add SYS-001",
    ]
    assert history.commits[0].author == "Tester"
    path.write_text("package 'SYS-001' {  }\n", encoding="utf-8")
    assert file_history(str(path)).change == "modified"


def test_02_outside_a_repository_there_is_an_error(tmp_path):
    path = tmp_path / "SYS-001.sysml"
    path.write_text("package 'SYS-001' {}\n", encoding="utf-8")
    history = file_history(str(path))
    assert history.commits == []
    assert history.error is not None
