"""
@relation(SDOC-SRS-210, SDOC-SRS-212, SDOC-SRS-213, SDOC-SRS-214, scope=file)
"""

import ipaddress
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from strictdoc.core.file_system.document_finder import get_document_extensions
from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.diff_and_changelog.git_client import (
    FileStatus,
    FileStatusKind,
    GitClient,
    GitCommandResult,
)
from strictdoc.helpers.path_filter import PathFilter

ASSETS_DIRECTORY_NAME = "_assets"

# The document finder never descends into these directories.
DOCUMENT_FINDER_SKIPPED_DIRECTORIES = ("output", "Output")

# The asset directory finder never descends into these directories, or into
# a directory whose name starts with "__".
ASSET_FINDER_SKIPPED_DIRECTORIES = ("build", "output", "Output", "tests")


@dataclass(frozen=True)
class UnpublishedChange:
    # Relative to the Git root, with "/" as the separator.
    path: str
    full_path: str
    kind: FileStatusKind
    is_untracked: bool
    # None for a non-document file or a document that is not on disk.
    document_title: Optional[str]

    def get_display_name(self) -> str:
        if self.document_title is not None and len(self.document_title) > 0:
            return self.document_title
        return self.path


@dataclass(frozen=True)
class DiscardResult:
    change: UnpublishedChange
    # None if StrictDoc deleted an untracked file without running Git.
    command_result: Optional[GitCommandResult]
    error_message: Optional[str]

    def is_success(self) -> bool:
        return self.error_message is None


class GitPublishService:
    """
    Find, list and discard unpublished changes to managed files.

    A managed file is a document file or a file in an "_assets" directory,
    located under one of the project's input paths. StrictDoc never reads,
    discards or commits any other file.
    """

    def __init__(
        self,
        *,
        project_config: ProjectConfig,
        path_to_git_root: Optional[str],
    ) -> None:
        assert project_config.input_paths is not None
        self.project_config: ProjectConfig = project_config
        self.path_to_git_root: Optional[str] = path_to_git_root
        self.git_client: Optional[GitClient] = (
            GitClient(path_to_git_root)
            if path_to_git_root is not None
            else None
        )
        self._document_extensions: Tuple[str, ...] = tuple(
            get_document_extensions(project_config)
        )
        self._path_filter_includes = PathFilter(
            project_config.include_doc_paths, positive_or_negative=True
        )
        self._path_filter_excludes = PathFilter(
            project_config.exclude_doc_paths, positive_or_negative=False
        )
        self._output_dir: Optional[str] = (
            os.path.realpath(project_config.output_dir)
            if project_config.output_dir is not None
            else None
        )
        self._input_paths: List[str] = [
            os.path.realpath(input_path_)
            for input_path_ in project_config.input_paths
        ]

    @staticmethod
    def create(project_config: ProjectConfig) -> "GitPublishService":
        """
        Resolve the Git root once from the project directory. If the project
        is not in a Git working tree, the service is created as unavailable.
        """

        project_directory = os.path.realpath(
            project_config.get_project_root_path()
        )
        if os.path.isfile(project_directory):
            project_directory = os.path.dirname(project_directory)
        path_to_git_root = (
            GitClient.find_git_root(project_directory)
            if os.path.isdir(project_directory)
            else None
        )
        return GitPublishService(
            project_config=project_config,
            path_to_git_root=path_to_git_root,
        )

    def is_available(self) -> bool:
        return self.git_client is not None

    def is_write_allowed(self) -> bool:
        """
        Discard and publish change files on disk. A server that can be
        reached from the network must not offer them, because the server has
        no authentication.
        """

        return is_loopback_host(self.project_config.server_host)

    def get_unpublished_changes(
        self, document_titles_by_full_path: Dict[str, str]
    ) -> List[UnpublishedChange]:
        """
        Return the managed files that differ from HEAD, sorted by path.
        document_titles_by_full_path maps a document's real path to its title.
        """

        if self.git_client is None:
            return []

        git_status_result = self.git_client.get_status(
            self._get_input_pathspecs()
        )
        unpublished_changes: List[UnpublishedChange] = []
        for file_status_ in git_status_result.file_statuses:
            full_path = self._get_full_path(file_status_.path)
            if not self.is_managed_file(full_path):
                continue
            unpublished_changes.append(
                self._create_unpublished_change(
                    file_status_, full_path, document_titles_by_full_path
                )
            )
        unpublished_changes.sort(key=lambda change_: change_.path)
        return unpublished_changes

    def find_unpublished_change(
        self, path: str, document_titles_by_full_path: Dict[str, str]
    ) -> Optional[UnpublishedChange]:
        """
        Return the current unpublished change for a path from a request, or
        None if the path is not a changed managed file. Callers must use this
        to validate any path that comes from a client.
        """

        for change_ in self.get_unpublished_changes(
            document_titles_by_full_path
        ):
            if change_.path == path:
                return change_
        return None

    def discard_change(self, change: UnpublishedChange) -> DiscardResult:
        """
        Restore a tracked file to its state in HEAD, or delete an untracked
        new file.
        """

        assert self.git_client is not None
        assert self.is_managed_file(change.full_path), change

        if change.is_untracked:
            try:
                os.remove(change.full_path)
            except OSError as os_error:
                return DiscardResult(
                    change=change,
                    command_result=None,
                    error_message=f"Could not delete the file: {os_error}.",
                )
            return DiscardResult(
                change=change, command_result=None, error_message=None
            )

        command_result = self.git_client.restore_paths([change.path])
        if not command_result.is_success():
            return DiscardResult(
                change=change,
                command_result=command_result,
                error_message="Git could not restore the file.",
            )
        return DiscardResult(
            change=change, command_result=command_result, error_message=None
        )

    def is_managed_file(self, full_path: str) -> bool:
        full_path = os.path.realpath(full_path)
        if self._output_dir is not None and _is_path_inside(
            full_path, self._output_dir
        ):
            return False

        for input_path_ in self._input_paths:
            if os.path.isfile(input_path_):
                if self._is_managed_file_for_input_file(full_path, input_path_):
                    return True
                continue
            if not _is_path_inside(full_path, input_path_):
                continue
            relative_path = os.path.relpath(full_path, input_path_).replace(
                os.sep, "/"
            )
            if self._is_managed_document(relative_path):
                return True
            if self._is_managed_asset(relative_path):
                return True
        return False

    def is_document_file(self, full_path: str) -> bool:
        return full_path.endswith(self._document_extensions)

    def _get_input_pathspecs(self) -> List[str]:
        assert self.path_to_git_root is not None
        pathspecs: List[str] = []
        for input_path_ in self._input_paths:
            if not _is_path_inside(input_path_, self.path_to_git_root) and (
                input_path_ != self.path_to_git_root
            ):
                continue
            pathspec_path = input_path_
            # A single-file input path also owns the "_assets" directory next
            # to it.
            if os.path.isfile(input_path_):
                pathspec_path = os.path.dirname(input_path_)
            relative_path = os.path.relpath(
                pathspec_path, self.path_to_git_root
            ).replace(os.sep, "/")
            pathspecs.append(relative_path)
        return pathspecs

    def _get_full_path(self, path_relative_to_git_root: str) -> str:
        assert self.path_to_git_root is not None
        return os.path.join(
            self.path_to_git_root,
            path_relative_to_git_root.replace("/", os.sep),
        )

    def _create_unpublished_change(
        self,
        file_status: FileStatus,
        full_path: str,
        document_titles_by_full_path: Dict[str, str],
    ) -> UnpublishedChange:
        return UnpublishedChange(
            path=file_status.path,
            full_path=full_path,
            kind=file_status.kind,
            is_untracked=file_status.is_untracked,
            document_title=document_titles_by_full_path.get(
                os.path.realpath(full_path)
            ),
        )

    def _is_managed_file_for_input_file(
        self, full_path: str, input_file_path: str
    ) -> bool:
        if full_path == input_file_path:
            return True
        assets_directory = os.path.join(
            os.path.dirname(input_file_path), ASSETS_DIRECTORY_NAME
        )
        return _is_path_inside(full_path, assets_directory)

    def _is_managed_document(self, relative_path: str) -> bool:
        """
        Mirror the rules of FileFinder.find_files_with_extensions().
        """

        if not relative_path.endswith(self._document_extensions):
            return False
        directory_names = relative_path.split("/")[:-1]
        directory_relative_path = ""
        for directory_name_ in directory_names:
            if directory_name_ in DOCUMENT_FINDER_SKIPPED_DIRECTORIES:
                return False
            directory_relative_path += directory_name_ + "/"
            if self._path_filter_excludes.match(directory_relative_path):
                return False
        if self._path_filter_excludes.match(relative_path):
            return False
        return self._path_filter_includes.match(relative_path)

    def _is_managed_asset(self, relative_path: str) -> bool:
        """
        Mirror the rules of PathFinder.find_directories() for "_assets".
        """

        directory_names = relative_path.split("/")[:-1]
        if ASSETS_DIRECTORY_NAME not in directory_names:
            return False
        directory_relative_path = ""
        for directory_name_ in directory_names:
            if directory_name_ == ASSETS_DIRECTORY_NAME:
                return True
            if (
                directory_name_.startswith("__")
                or directory_name_ in ASSET_FINDER_SKIPPED_DIRECTORIES
            ):
                return False
            directory_relative_path += directory_name_ + "/"
            if self._path_filter_excludes.match(
                directory_relative_path
            ) or not self._path_filter_includes.match(directory_relative_path):
                return False
        return False  # pragma: no cover


def is_loopback_host(host: str) -> bool:
    for scheme_ in ("http://", "https://"):
        if host.startswith(scheme_):
            host = host[len(scheme_) :]
    host = host.strip("[]")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_path_inside(path: str, directory: str) -> bool:
    return path.startswith(directory.rstrip(os.sep) + os.sep)
