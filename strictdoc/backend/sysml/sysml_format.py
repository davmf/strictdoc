"""
Experimental SysML v2 document format.

Not part of ProjectConfig.default_formats(). A project opts in via
strictdoc_config.py:

    ProjectConfig(formats=[*ProjectConfig.default_formats(), SysMLFormat()])

SysMLFormat(item_versioning=True) turns on item versioning: StrictDoc
versions requirements and design elements when it saves them, pins new
traces to the version of their target, and warns about suspect traces. See
versioning.py and version_tracking.py.

Requirement attributes typed by an `enum def` are SingleChoice fields, which
the edit form shows as drop-down lists. See choices.py.

SysMLFormat(tracker_layout=True) reads the tracker layout, one file per
item: each tracker file is a document made of the files it includes, and
the other files are not documents. See tracker.py. The files that no
tracker includes are libraries: their `enum def` elements give the options
of choice fields, and a StrictDocVersioning package among them is the
versioning library.
"""

import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sysml import (
    choices,
    node_data,
    tracker,
    version_tracking,
    versioning,
)
from strictdoc.backend.sysml.model import SysMLPackage
from strictdoc.backend.sysml.parser import SysMLParser
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.backend.sysml.version_tracking import TargetVersionLookup
from strictdoc.backend.sysml.writer import SysMLTrackerWriter, SysMLWriter
from strictdoc.core.file_system.file_tree import File
from strictdoc.core.format import ExportContext, Format
from strictdoc.core.project_config import ProjectConfig

if TYPE_CHECKING:
    from strictdoc.core.traceability_index import TraceabilityIndex


class SysMLFormat(Format):
    def __init__(
        self, item_versioning: bool = False, tracker_layout: bool = False
    ) -> None:
        self.item_versioning: bool = item_versioning
        self.tracker_layout: bool = tracker_layout
        # The latest traceability index, to look up the current version of
        # a trace target in another document.
        self._traceability_index: Optional[TraceabilityIndex] = None
        # Tracker layout: the .sysml files that are not trackers. Those that
        # no tracker includes are libraries.
        self._other_files: Set[str] = set()
        # The top-level package names of the libraries, after the index is
        # built.
        self._library_package_names: Set[str] = set()

    def __getstate__(self) -> Dict[str, Any]:
        # The project config, and with it this format, is pickled for
        # parallel reading. The index is not needed there.
        state = dict(self.__dict__)
        state["_traceability_index"] = None
        return state

    @staticmethod
    def handles() -> List[str]:
        return ["sysml"]

    @staticmethod
    def supported_extensions() -> List[str]:
        return [".sysml"]

    @staticmethod
    def supports_import() -> bool:
        return False

    @staticmethod
    def supports_export() -> bool:
        return False

    @staticmethod
    def supports_read() -> bool:
        return True

    @staticmethod
    def supports_edit() -> bool:
        return True

    @staticmethod
    def read_extensions() -> List[str]:
        return [".sysml"]

    def is_document_file(self, path: str) -> bool:
        if self.tracker_layout:
            if tracker.is_tracker_file(path):
                return True
            self._other_files.add(os.path.abspath(path))
            return False
        return True

    def read_from_file(
        self, doc_file: File, project_config: ProjectConfig
    ) -> SDocDocument:
        if self.tracker_layout:
            return SysMLReader.read_from_tracker_file(
                doc_file.full_path,
                relative_path=doc_file.rel_path.relative_path_posix,
                item_versioning=self.item_versioning,
                static_directory=project_config.dir_for_sdoc_assets,
            )
        return SysMLReader.read_from_file(
            doc_file.full_path,
            project_config,
            relative_path=doc_file.rel_path.relative_path_posix,
            item_versioning=self.item_versioning,
        )

    def write_document_to_file(
        self,
        document: SDocDocument,
        project_config: ProjectConfig,
    ) -> None:
        if self.item_versioning:
            version_tracking.update_requirement_versions(
                document, self.target_version_lookup(document)
            )
            self.ensure_library(project_config)
        if node_data.get_tracker(document) is not None:
            SysMLTrackerWriter.write_to_files(document)
        else:
            SysMLWriter.write_to_file(document)
        SysMLReader.refresh_diagram(
            document,
            project_config.dir_for_sdoc_assets
            if project_config is not None
            else "_static",
        )

    def traceability_index_build_finished(
        self, traceability_index: "TraceabilityIndex"
    ) -> None:
        self._traceability_index = traceability_index
        library_definitions: choices.EnumDefinitions = {}
        if self.tracker_layout:
            library_definitions = self._read_libraries(traceability_index)
        choices.apply_choice_fields(traceability_index, library_definitions)
        if self.item_versioning:
            version_tracking.report_issues(traceability_index)
        if self.tracker_layout:
            _report_layout_issues(traceability_index)

    def target_version_lookup(
        self, document: Optional[SDocDocument] = None
    ) -> TargetVersionLookup:
        return version_tracking.index_target_version_lookup(
            self._traceability_index, document
        )

    def ensure_library(self, project_config: ProjectConfig) -> Optional[str]:
        """
        Write the StrictDocVersioning library to the project root, unless
        the project already has it. Returns the path when it was written.
        """
        if (
            versioning.LIBRARY_PACKAGE in self._library_package_names
            or version_tracking.has_library(self._traceability_index)
        ):
            return None
        if (
            project_config.input_paths is None
            or len(project_config.input_paths) == 0
        ):
            return None
        project_root = project_config.input_paths[0]
        if not os.path.isdir(project_root):
            project_root = os.path.dirname(project_root)
        return versioning.ensure_library(project_root)

    def _read_libraries(
        self, traceability_index: "TraceabilityIndex"
    ) -> choices.EnumDefinitions:
        """
        Read the files that no tracker includes. Returns their enum
        definitions and records their top-level package names.
        """
        included: Set[str] = set()
        for document_ in traceability_index.document_tree.document_list:
            tracker_data = node_data.get_tracker(document_)
            if tracker_data is not None:
                included.update(
                    os.path.abspath(path_) for path_ in tracker_data.file_paths
                )
        definitions: choices.EnumDefinitions = {}
        package_names: Set[str] = set()
        for path_ in sorted(self._other_files - included):
            if not os.path.isfile(path_):
                continue
            try:
                model = SysMLParser.parse_file(path_)
            except Exception:  # noqa: BLE001
                # The Pilot reports a broken library. StrictDoc reads only
                # the choices and the versioning library from it.
                continue
            definitions.update(choices.collect_enum_definitions(model))
            package_names.update(
                member_.name
                for member_ in model.members
                if isinstance(member_, SysMLPackage)
                and member_.name is not None
            )
        self._library_package_names = package_names
        return definitions

    @staticmethod
    def supports_grammar() -> bool:
        return False

    def export_complete_tree(
        self,
        context: ExportContext,  # noqa: ARG002
        handle: str,  # noqa: ARG002
    ) -> None:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support export."
        )


def _report_layout_issues(traceability_index: "TraceabilityIndex") -> None:
    """
    Report, on the tracker documents, the files of their directories that
    no tracker includes and the IDs that two files of the trackers share.
    The Pilot reports neither: a file nothing imports is never checked, and
    two top-level packages with one name resolve to either of them.
    """
    trackers: Dict[str, SDocDocument] = {}
    files_by_id: Dict[str, List[str]] = {}
    included_files: Set[str] = set()
    for document_ in traceability_index.document_tree.document_list:
        tracker_data = node_data.get_tracker(document_)
        if tracker_data is None:
            continue
        trackers[os.path.dirname(tracker_data.tracker.file_path)] = document_
        for path_ in tracker_data.file_paths:
            included_files.add(path_)
            file_id = os.path.splitext(os.path.basename(path_))[0]
            files_by_id.setdefault(file_id, []).append(path_)
    for directory_, document_ in trackers.items():
        for file_ in sorted(os.listdir(directory_)):
            path_ = os.path.join(directory_, file_)
            if not file_.endswith(".sysml") or path_ in included_files:
                continue
            if tracker.is_tracker_file(path_):
                continue
            traceability_index.validation_index.add_issue(
                document_,
                f"SysML file {file_} is in the tracker directory, but no "
                "tracker or folder includes it.",
            )
    for file_id_, paths_ in files_by_id.items():
        if len(paths_) < 2:
            continue
        for directory_, document_ in trackers.items():
            if any(os.path.dirname(path_) == directory_ for path_ in paths_):
                traceability_index.validation_index.add_issue(
                    document_,
                    f"SysML ID '{file_id_}' is used by more than one file: "
                    + ", ".join(sorted(paths_))
                    + ".",
                )


def versioning_format_for_document(
    project_config: ProjectConfig, document: SDocDocument
) -> Optional[SysMLFormat]:
    """
    The SysML format of a document when it has item versioning, or None.
    """
    if document.meta is None:
        return None
    document_format = project_config.get_editable_format_for_path(
        document.meta.input_doc_full_path
    )
    if isinstance(document_format, SysMLFormat) and (
        document_format.item_versioning
    ):
        return document_format
    return None
