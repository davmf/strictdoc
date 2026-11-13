"""
Typst export, and PDF export through Typst.

The export writes one .typ file per document into a single folder, together
with strictdoc.typ, the report template and the project assets. The files
are not nested in subfolders, so that a build image can compile every report
.typ file of a single folder.
"""

import os
import re
import shutil
from pathlib import Path
from typing import List, Set

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.typst.pdf_builder import TypstPDFBuilder
from strictdoc.backend.typst.typst_files import (
    PATH_TO_STRICTDOC_REPORT_TYP,
    PATH_TO_STRICTDOC_TYP,
    get_template_file_name_bases,
)
from strictdoc.backend.typst.writer import TypstWriter
from strictdoc.core.format import ExportContext, Format
from strictdoc.core.project_config import ProjectConfig
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.export.html.html_generator import HTMLGenerator


class TypstFormat(Format):
    @staticmethod
    def handles() -> List[str]:
        return ["typst", "typst-pdf"]

    @staticmethod
    def supported_extensions() -> List[str]:
        return [".typ"]

    @staticmethod
    def supports_import() -> bool:
        return False

    @staticmethod
    def supports_export() -> bool:
        return True

    @staticmethod
    def supports_read() -> bool:
        return False

    @staticmethod
    def supports_edit() -> bool:
        return False

    @staticmethod
    def supports_grammar() -> bool:
        return False

    def export_complete_tree(self, context: ExportContext, handle: str) -> None:
        assert handle in self.handles(), handle
        project_config = context.project_config
        traceability_index = context.traceability_index

        documents = [
            document_
            for document_ in traceability_index.document_tree.document_list
            if project_config.export_included_documents
            or not document_.document_is_included()
        ]
        # "typst-pdf" writes the same .typ files to their own folder and
        # compiles them there, so the PDFs sit next to the sources.
        dir_name = "typst" if handle == "typst" else "typst-pdf"
        path_to_output_dir = os.path.join(project_config.output_dir, dir_name)
        warnings = self.export_documents(
            traceability_index=traceability_index,
            project_config=project_config,
            documents=documents,
            path_to_output_dir=path_to_output_dir,
        )
        for warning_ in warnings:
            print(f"warning: Typst export: {warning_}")  # noqa: T201

        if handle == "typst-pdf":
            paths_to_pdf = TypstPDFBuilder.build(
                project_config, path_to_output_dir
            )
            for path_to_pdf_ in paths_to_pdf:
                print(f"Typst PDF: {path_to_pdf_}")  # noqa: T201

    @classmethod
    def export_documents(
        cls,
        *,
        traceability_index: TraceabilityIndex,
        project_config: ProjectConfig,
        documents: List[SDocDocument],
        path_to_output_dir: str,
    ) -> List[str]:
        """
        Write the .typ files of the documents, strictdoc.typ and the project
        assets into one folder. Return the warnings of the export.
        """
        Path(path_to_output_dir).mkdir(parents=True, exist_ok=True)

        # All assets go to one _assets folder, as for the HTML2PDF bundle,
        # because all documents sit in one folder.
        HTMLGenerator.export_project_assets(
            traceability_index=traceability_index,
            export_output_html_root=path_to_output_dir,
            flat_assets=True,
        )
        shutil.copyfile(
            PATH_TO_STRICTDOC_TYP,
            os.path.join(path_to_output_dir, "strictdoc.typ"),
        )
        if not project_config.is_typst_template_external():
            shutil.copyfile(
                PATH_TO_STRICTDOC_REPORT_TYP,
                os.path.join(path_to_output_dir, "strictdoc-report.typ"),
            )

        writer = TypstWriter(
            traceability_index=traceability_index,
            project_config=project_config,
            path_to_output_dir=path_to_output_dir,
        )
        used_file_names: Set[str] = set(
            get_template_file_name_bases(project_config)
        )
        for document_ in documents:
            assert document_.meta is not None
            file_name_base = cls._file_name_base(
                os.path.join(
                    document_.meta.input_doc_dir_rel_path.relative_path_posix,
                    document_.meta.document_filename_base,
                ),
                used_file_names,
            )
            output = writer.write(document_, diagram_name_prefix=file_name_base)
            path_to_output = os.path.join(
                path_to_output_dir, file_name_base + ".typ"
            )
            with open(path_to_output, "w", encoding="utf8") as output_file_:
                output_file_.write(output)
        return writer.warnings

    @staticmethod
    def _file_name_base(relative_path: str, used_file_names: Set[str]) -> str:
        """
        A file name from the path of the document in the project, for
        example "docs/srs" becomes "docs-srs". Diagram names of Kroki reuse
        it, so it keeps only letters, digits, "_" and "-".
        """
        name = re.sub(r"[^\w-]+", "-", relative_path).strip("-")
        if len(name) == 0:
            name = "document"
        unique_name = name
        suffix = 2
        while unique_name in used_file_names:
            unique_name = f"{name}-{suffix}"
            suffix += 1
        used_file_names.add(unique_name)
        return unique_name
