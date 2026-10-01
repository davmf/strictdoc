"""
@relation(SDOC-SRS-209, SDOC-SRS-210, scope=file)
"""

import os

import pytest

from strictdoc.features.diff_and_changelog.git_client import (
    FileStatus,
    FileStatusKind,
    GitClient,
)
from tests.unit.strictdoc.features.git_publish.git_repository import (
    GitRepository,
)


@pytest.fixture
def repository(tmp_path) -> GitRepository:
    repository = GitRepository(str(tmp_path))
    repository.write_file("docs/a.sdoc", "A\n")
    repository.write_file("docs/b c.sdoc", "B C\n")
    repository.write_file("docs/keep.sdoc", "KEEP\n")
    repository.commit_all("Initial commit")
    return repository


def test_find_git_root_from_subdirectory(repository: GitRepository) -> None:
    path_to_subdirectory = os.path.join(repository.path_to_root, "docs")
    assert (
        GitClient.find_git_root(path_to_subdirectory) == repository.path_to_root
    )


def test_find_git_root_outside_git_returns_none(tmp_path, monkeypatch) -> None:
    path_to_directory = tmp_path / "not_a_repository"
    path_to_directory.mkdir()
    # Stop Git from finding a repository in a parent of the temp directory.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert GitClient.find_git_root(str(path_to_directory)) is None


def test_get_status_clean_tree(repository: GitRepository) -> None:
    git_client = GitClient(repository.path_to_root)
    git_status_result = git_client.get_status(["docs"])
    assert git_status_result.command_result is not None
    assert git_status_result.command_result.is_success()
    assert git_status_result.file_statuses == []


def test_get_status_without_paths_does_not_run_git(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/a.sdoc", "A modified\n")
    git_client = GitClient(repository.path_to_root)
    git_status_result = git_client.get_status([])
    assert git_status_result.command_result is None
    assert git_status_result.file_statuses == []


def test_get_status_modified_new_deleted_and_space_in_path(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/a.sdoc", "A modified\n")
    repository.write_file("docs/new file.sdoc", "NEW\n")
    repository.delete_file("docs/b c.sdoc")

    git_client = GitClient(repository.path_to_root)
    git_status_result = git_client.get_status(["docs"])

    assert sorted(
        git_status_result.file_statuses, key=lambda status_: status_.path
    ) == [
        FileStatus("docs/a.sdoc", FileStatusKind.MODIFIED, False),
        FileStatus("docs/b c.sdoc", FileStatusKind.DELETED, False),
        FileStatus("docs/new file.sdoc", FileStatusKind.NEW, True),
    ]


def test_get_status_staged_new_file(repository: GitRepository) -> None:
    repository.write_file("docs/staged.sdoc", "STAGED\n")
    repository.run(["add", "docs/staged.sdoc"])

    git_client = GitClient(repository.path_to_root)
    git_status_result = git_client.get_status(["docs"])

    assert git_status_result.file_statuses == [
        FileStatus("docs/staged.sdoc", FileStatusKind.NEW, False),
    ]


def test_get_status_rename_gives_deleted_and_new(
    repository: GitRepository,
) -> None:
    repository.run(["mv", "docs/a.sdoc", "docs/renamed.sdoc"])

    git_client = GitClient(repository.path_to_root)
    git_status_result = git_client.get_status(["docs"])

    assert git_status_result.file_statuses == [
        FileStatus("docs/renamed.sdoc", FileStatusKind.NEW, False),
        FileStatus("docs/a.sdoc", FileStatusKind.DELETED, False),
    ]


def test_get_status_is_limited_to_given_paths(
    repository: GitRepository,
) -> None:
    repository.write_file("notes.txt", "NOTES\n")
    repository.write_file("docs/a.sdoc", "A modified\n")

    git_client = GitClient(repository.path_to_root)
    git_status_result = git_client.get_status(["docs"])

    assert [status_.path for status_ in git_status_result.file_statuses] == [
        "docs/a.sdoc"
    ]


def test_restore_paths_modified_and_deleted(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/a.sdoc", "A modified\n")
    repository.delete_file("docs/b c.sdoc")
    repository.write_file("docs/keep.sdoc", "KEEP modified\n")

    git_client = GitClient(repository.path_to_root)
    command_result = git_client.restore_paths(["docs/a.sdoc", "docs/b c.sdoc"])

    assert command_result.is_success(), command_result
    assert command_result.command[:2] == ["git", "--literal-pathspecs"]
    assert repository.read_file("docs/a.sdoc") == "A\n"
    assert repository.read_file("docs/b c.sdoc") == "B C\n"
    # A path that was not passed is left alone.
    assert repository.read_file("docs/keep.sdoc") == "KEEP modified\n"


def test_restore_paths_staged_new_file_is_removed(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/staged.sdoc", "STAGED\n")
    repository.run(["add", "docs/staged.sdoc"])

    git_client = GitClient(repository.path_to_root)
    command_result = git_client.restore_paths(["docs/staged.sdoc"])

    assert command_result.is_success(), command_result
    assert not repository.exists("docs/staged.sdoc")
    assert repository.get_porcelain_status() == ""


def test_restore_paths_staged_and_unstaged_changes(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/a.sdoc", "A staged\n")
    repository.run(["add", "docs/a.sdoc"])
    repository.write_file("docs/a.sdoc", "A staged and modified\n")

    git_client = GitClient(repository.path_to_root)
    command_result = git_client.restore_paths(["docs/a.sdoc"])

    assert command_result.is_success(), command_result
    assert repository.read_file("docs/a.sdoc") == "A\n"
    assert repository.get_porcelain_status() == ""


def test_restore_paths_does_not_expand_wildcards(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/a.sdoc", "A modified\n")

    git_client = GitClient(repository.path_to_root)
    command_result = git_client.restore_paths(["docs/*.sdoc"])

    assert not command_result.is_success()
    assert "did not match" in command_result.stderr
    assert repository.read_file("docs/a.sdoc") == "A modified\n"


def test_restore_paths_requires_paths(repository: GitRepository) -> None:
    git_client = GitClient(repository.path_to_root)
    with pytest.raises(AssertionError):
        git_client.restore_paths([])
