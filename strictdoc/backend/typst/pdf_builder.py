"""
Compiles exported .typ files to PDF with the company typst-doc-builder image.

The image compiles every report .typ file of the folder that is mounted at
/work and writes each PDF next to it, named "<doc_no>_<version>-<title>.pdf".
"""

import glob
import os
import shutil
import subprocess
from typing import List

from strictdoc.core.project_config import ProjectConfig

TYPST_PDF_BUILD_TIMEOUT_SECONDS = 300

# The end of the builder output that an error message shows.
_OUTPUT_TAIL_LENGTH = 2000


class TypstPDFBuilderError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message: str = message


class TypstPDFBuilder:
    @staticmethod
    def get_command(
        project_config: ProjectConfig, path_to_dir: str
    ) -> List[str]:
        if project_config.typst_pdf_command is not None:
            return [
                item_.replace("{dir}", path_to_dir)
                for item_ in project_config.typst_pdf_command
            ]
        command = ["docker", "run", "--rm"]
        # Without this, the PDF files in the mounted folder belong to root.
        if hasattr(os, "getuid") and hasattr(os, "getgid"):
            command += ["-u", f"{os.getuid()}:{os.getgid()}"]
        command += [
            "-v",
            f"{path_to_dir}:/work",
            project_config.typst_pdf_builder_image,
        ]
        return command

    @classmethod
    def build(
        cls, project_config: ProjectConfig, path_to_dir: str
    ) -> List[str]:
        """Compile the folder and return the paths of the PDF files."""
        command = cls.get_command(project_config, path_to_dir)
        if shutil.which(command[0]) is None:
            raise TypstPDFBuilderError(
                f"Typst PDF: the command '{command[0]}' is not installed or "
                "is not on the PATH of the StrictDoc server."
            )
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=TYPST_PDF_BUILD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exception_:
            raise TypstPDFBuilderError(
                "Typst PDF: the build took longer than "
                f"{TYPST_PDF_BUILD_TIMEOUT_SECONDS} seconds."
            ) from exception_
        output = (result.stdout or "") + (result.stderr or "")
        print(output, end="")  # noqa: T201
        if result.returncode != 0:
            hint = ""
            if "Unable to find image" in output:
                hint = (
                    "\n\nDocker cannot find or pull the builder image "
                    f"'{project_config.typst_pdf_builder_image}'. Build it "
                    "locally, for example with 'docker build -t "
                    "typst-doc-builder:local <typst-doc-builder folder>', and "
                    "set typst_pdf_builder_image in the project config."
                )
            raise TypstPDFBuilderError(
                f"Typst PDF: the build failed with exit code "
                f"{result.returncode}:\n\n{output[-_OUTPUT_TAIL_LENGTH:]}"
                f"{hint}"
            )
        paths_to_pdf = sorted(glob.glob(os.path.join(path_to_dir, "*.pdf")))
        if len(paths_to_pdf) == 0:
            raise TypstPDFBuilderError(
                "Typst PDF: the build wrote no PDF file:\n\n"
                f"{output[-_OUTPUT_TAIL_LENGTH:]}"
            )
        return paths_to_pdf
