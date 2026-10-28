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
"""

import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sysml import choices, version_tracking, versioning
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.backend.sysml.version_tracking import TargetVersionLookup
from strictdoc.backend.sysml.writer import SysMLWriter
from strictdoc.core.file_system.file_tree import File
from strictdoc.core.format import ExportContext, Format
from strictdoc.core.project_config import ProjectConfig

if TYPE_CHECKING:
    from strictdoc.core.traceability_index import TraceabilityIndex


class SysMLFormat(Format):
    def __init__(self, item_versioning: bool = False) -> None:
        self.item_versioning: bool = item_versioning
        # The latest traceability index, to look up the current version of
        # a trace target in another document.
        self._traceability_index: Optional[TraceabilityIndex] = None

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

    def read_from_file(
        self, doc_file: File, project_config: ProjectConfig
    ) -> SDocDocument:
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
        SysMLWriter.write_to_file(document)
        SysMLReader.refresh_diagram(document)

    def traceability_index_build_finished(
        self, traceability_index: "TraceabilityIndex"
    ) -> None:
        self._traceability_index = traceability_index
        choices.apply_choice_fields(traceability_index)
        if self.item_versioning:
            version_tracking.report_issues(traceability_index)

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
        if version_tracking.has_library(self._traceability_index):
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
