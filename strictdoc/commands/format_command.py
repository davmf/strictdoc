import argparse
import sys
from typing import Optional

from strictdoc.backend.sdoc.errors.document_tree_error import DocumentTreeError
from strictdoc.cli.base_command import BaseCommand, CLIValidationError
from strictdoc.commands.format_config import FormatCommandConfig
from strictdoc.core.format import Format
from strictdoc.core.project_config import ProjectConfig, ProjectConfigLoader
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.core.traceability_index_builder import TraceabilityIndexBuilder
from strictdoc.helpers.parallelizer import Parallelizer


class FormatCommand(BaseCommand):
    HELP = "Format editable documents to the configured line width."
    DETAILED_HELP = """\
This command reads all documents in the project tree that an editable format
can write, such as SDoc and Markdown, and writes them back formatted
according to the project's `document_line_width` configuration option (set
in strictdoc_config.py).

If `document_line_width` is not configured, the command still rewrites all
documents to normalise their content (a no-op round-trip).
"""

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "input_path",
            type=str,
            help="Path to the project tree.",
        )
        parser.add_argument(
            "--config",
            type=str,
            help="Path to the StrictDoc TOML config file.",
        )

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.config: FormatCommandConfig = FormatCommandConfig(**vars(args))

    def run(self, parallelizer: Parallelizer) -> None:
        format_config: FormatCommandConfig = self.config
        try:
            format_config.validate()
        except CLIValidationError as exception_:
            raise exception_

        project_config: ProjectConfig = (
            ProjectConfigLoader.load_using_format_config(format_config)
        )

        try:
            traceability_index: TraceabilityIndex = (
                TraceabilityIndexBuilder.create(
                    project_config=project_config,
                    parallelizer=parallelizer,
                    skip_source_files=True,
                )
            )
        except DocumentTreeError as exc:
            print(exc.to_print_message())  # noqa: T201
            sys.exit(1)

        for document in traceability_index.document_tree.document_list:
            assert document.meta is not None

            if document.autogen:
                continue

            document_format: Optional[Format] = (
                project_config.get_editable_format_for_path(
                    document.meta.input_doc_full_path
                )
            )
            if document_format is None:
                continue
            document_format.write_document_to_file(document, project_config)
