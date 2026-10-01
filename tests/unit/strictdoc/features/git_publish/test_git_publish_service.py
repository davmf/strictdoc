"""
@relation(SDOC-SRS-208, SDOC-SRS-210, SDOC-SRS-212, scope=file)
@relation(SDOC-SRS-213, SDOC-SRS-214, scope=file)
"""

import os
from typing import List, Optional

import pytest

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.diff_and_changelog.git_client import FileStatusKind
from strictdoc.features.git_publish.git_publish_service import (
    GitPublishService,
    UnpublishedChange,
    is_loopback_host,
)
from tests.unit.strictdoc.features.git_publish.git_repository import (
    GitRepository,
)


@pytest.fixture
def repository(tmp_path) -> GitRepository:
    repository = GitRepository(str(tmp_path))
    repository.write_file("docs/requirements.sdoc", "REQUIREMENTS\n")
    repository.write_file("docs/notes.txt", "NOTES\n")
    repository.write_file("docs/_assets/image.png", "IMAGE\n")
    repository.write_file("README.md", "README\n")
    repository.commit_all("Initial commit")
    return repository


def _create_service(
    repository: GitRepository,
    *,
    input_paths: Optional[List[str]] = None,
    exclude_doc_paths: Optional[List[str]] = None,
    server_host: str = "127.0.0.1",
) -> GitPublishService:
    project_config = ProjectConfig(
        input_paths=(
            input_paths
            if input_paths is not None
            else [os.path.join(repository.path_to_root, "docs")]
        ),
        exclude_doc_paths=exclude_doc_paths,
        server_host=server_host,
    )
    project_config.output_dir = os.path.join(
        repository.path_to_root, "docs", "build_output"
    )
    return GitPublishService.create(project_config)


def _get_paths(unpublished_changes: List[UnpublishedChange]) -> List[str]:
    return [change_.path for change_ in unpublished_changes]


def test_service_is_unavailable_outside_git(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    path_to_docs = tmp_path / "docs"
    path_to_docs.mkdir()
    project_config = ProjectConfig(input_paths=[str(path_to_docs)])

    git_publish_service = GitPublishService.create(project_config)

    assert not git_publish_service.is_available()
    assert git_publish_service.get_unpublished_changes({}) == []


def test_clean_tree_has_no_unpublished_changes(
    repository: GitRepository,
) -> None:
    git_publish_service = _create_service(repository)
    assert git_publish_service.is_available()
    assert git_publish_service.get_unpublished_changes({}) == []


def test_only_managed_files_are_listed(repository: GitRepository) -> None:
    repository.write_file("docs/requirements.sdoc", "MODIFIED\n")
    repository.write_file("docs/notes.txt", "MODIFIED\n")
    repository.write_file("docs/untracked.txt", "UNTRACKED\n")
    repository.write_file("docs/_assets/image.png", "MODIFIED\n")
    repository.write_file("docs/_assets/new_image.png", "NEW\n")
    repository.write_file("README.md", "MODIFIED\n")
    repository.write_file("other/outside.sdoc", "OUTSIDE\n")
    repository.write_file("docs/build_output/generated.sdoc", "GENERATED\n")
    repository.write_file("docs/output/skipped.sdoc", "SKIPPED\n")

    git_publish_service = _create_service(repository)
    unpublished_changes = git_publish_service.get_unpublished_changes({})

    assert _get_paths(unpublished_changes) == [
        "docs/_assets/image.png",
        "docs/_assets/new_image.png",
        "docs/requirements.sdoc",
    ]


def test_excluded_document_paths_are_not_managed(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/drafts/draft.sdoc", "DRAFT\n")
    repository.write_file("docs/requirements.sdoc", "MODIFIED\n")

    git_publish_service = _create_service(
        repository, exclude_doc_paths=["drafts/"]
    )

    assert _get_paths(git_publish_service.get_unpublished_changes({})) == [
        "docs/requirements.sdoc"
    ]


def test_single_file_input_path(repository: GitRepository) -> None:
    repository.write_file("docs/requirements.sdoc", "MODIFIED\n")
    repository.write_file("docs/other.sdoc", "OTHER\n")
    repository.write_file("docs/_assets/image.png", "MODIFIED\n")

    git_publish_service = _create_service(
        repository,
        input_paths=[
            os.path.join(repository.path_to_root, "docs", "requirements.sdoc")
        ],
    )

    assert _get_paths(git_publish_service.get_unpublished_changes({})) == [
        "docs/_assets/image.png",
        "docs/requirements.sdoc",
    ]


def test_change_kinds_and_document_titles(repository: GitRepository) -> None:
    repository.write_file("docs/requirements.sdoc", "MODIFIED\n")
    path_to_new_document = repository.write_file("docs/new.sdoc", "NEW\n")
    repository.delete_file("docs/_assets/image.png")

    git_publish_service = _create_service(repository)
    unpublished_changes = git_publish_service.get_unpublished_changes(
        {os.path.realpath(path_to_new_document): "New document"}
    )

    assert [
        (change_.path, change_.kind, change_.get_display_name())
        for change_ in unpublished_changes
    ] == [
        (
            "docs/_assets/image.png",
            FileStatusKind.DELETED,
            "docs/_assets/image.png",
        ),
        ("docs/new.sdoc", FileStatusKind.NEW, "New document"),
        (
            "docs/requirements.sdoc",
            FileStatusKind.MODIFIED,
            "docs/requirements.sdoc",
        ),
    ]


def test_find_unpublished_change_rejects_unmanaged_and_clean_paths(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/notes.txt", "MODIFIED\n")
    repository.write_file("docs/requirements.sdoc", "MODIFIED\n")

    git_publish_service = _create_service(repository)

    assert git_publish_service.find_unpublished_change(
        "docs/notes.txt", {}
    ) is (None)
    assert git_publish_service.find_unpublished_change("README.md", {}) is None
    assert (
        git_publish_service.find_unpublished_change(
            "docs/requirements.sdoc", {}
        )
        is not None
    )


def test_discard_modified_document_restores_head(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/requirements.sdoc", "MODIFIED\n")
    repository.write_file("docs/notes.txt", "NOTES MODIFIED\n")

    git_publish_service = _create_service(repository)
    unpublished_change = git_publish_service.find_unpublished_change(
        "docs/requirements.sdoc", {}
    )
    assert unpublished_change is not None
    discard_result = git_publish_service.discard_change(unpublished_change)

    assert discard_result.is_success(), discard_result
    assert repository.read_file("docs/requirements.sdoc") == "REQUIREMENTS\n"
    # The unmanaged file keeps its change.
    assert repository.read_file("docs/notes.txt") == "NOTES MODIFIED\n"


def test_discard_deleted_document_restores_it(
    repository: GitRepository,
) -> None:
    repository.delete_file("docs/requirements.sdoc")

    git_publish_service = _create_service(repository)
    unpublished_change = git_publish_service.find_unpublished_change(
        "docs/requirements.sdoc", {}
    )
    assert unpublished_change is not None
    assert unpublished_change.kind == FileStatusKind.DELETED
    discard_result = git_publish_service.discard_change(unpublished_change)

    assert discard_result.is_success(), discard_result
    assert repository.read_file("docs/requirements.sdoc") == "REQUIREMENTS\n"


def test_discard_new_untracked_document_deletes_it(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/new.sdoc", "NEW\n")
    repository.write_file("docs/untracked.txt", "UNTRACKED\n")

    git_publish_service = _create_service(repository)
    unpublished_change = git_publish_service.find_unpublished_change(
        "docs/new.sdoc", {}
    )
    assert unpublished_change is not None
    assert unpublished_change.is_untracked
    discard_result = git_publish_service.discard_change(unpublished_change)

    assert discard_result.is_success(), discard_result
    assert discard_result.command_result is None
    assert not repository.exists("docs/new.sdoc")
    assert repository.exists("docs/untracked.txt")


def test_server_on_project_subdirectory_uses_git_root(
    repository: GitRepository,
) -> None:
    repository.write_file("docs/requirements.sdoc", "MODIFIED\n")

    git_publish_service = _create_service(repository)

    assert git_publish_service.path_to_git_root == repository.path_to_root


@pytest.mark.parametrize(
    "host, expected_is_loopback",
    [
        ("127.0.0.1", True),
        ("127.0.0.2", True),
        ("::1", True),
        ("[::1]", True),
        ("localhost", True),
        ("http://127.0.0.1", True),
        ("0.0.0.0", False),
        ("192.168.1.10", False),
        ("example.com", False),
    ],
)
def test_is_loopback_host(host: str, expected_is_loopback: bool) -> None:
    assert is_loopback_host(host) == expected_is_loopback


def test_write_is_not_allowed_on_network_address(
    repository: GitRepository,
) -> None:
    assert _create_service(repository).is_write_allowed()
    assert not _create_service(
        repository, server_host="0.0.0.0"
    ).is_write_allowed()
