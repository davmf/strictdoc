"""
Experimental SysML v2 document format.

Not part of ProjectConfig.default_formats(). A project opts in via
strictdoc_config.py:

    ProjectConfig(formats=[*ProjectConfig.default_formats(), SysMLFormat()])
"""

from typing import List

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sysml.reader import SysMLReader
from strictdoc.backend.sysml.writer import SysMLWriter
from strictdoc.core.file_system.file_tree import File
from strictdoc.core.format import ExportContext, Format
from strictdoc.core.project_config import ProjectConfig


class SysMLFormat(Format):
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
        )

    def write_document_to_file(
        self,
        document: SDocDocument,
        project_config: ProjectConfig,  # noqa: ARG002
    ) -> None:
        SysMLWriter.write_to_file(document)
        SysMLReader.refresh_diagram(document)

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
