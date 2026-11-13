"""
Compiles exported .typ files to PDF.

There are three ways to build, chosen by the project config:

- typst_pdf_command: a command that compiles the folder of the .typ files
  and writes the PDF files into it.
- An external typst_template: the typst_pdf_builder_image image compiles
  the folder of the .typ files, which "docker run" mounts at /work, and
  writes the PDF files into it.
- The default, built-in template: "typst compile" compiles each document to
  a PDF with the name of its .typ file.
"""

import glob
import os
import shutil
import subprocess
import time
from typing import List

from strictdoc.backend.typst.typst_files import get_template_file_name_bases
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
        """The command that compiles the whole folder."""
        if project_config.typst_pdf_command is not None:
            return [
                item_.replace("{dir}", path_to_dir)
                for item_ in project_config.typst_pdf_command
            ]
        assert project_config.is_typst_template_external()
        if project_config.typst_pdf_builder_image is None:
            raise TypstPDFBuilderError(
                "Typst PDF: the external typst_template "
                f"'{project_config.typst_template}' needs the "
                "typst_pdf_builder_image option, or typst_pdf_command, in "
                "the project config."
            )
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

    @staticmethod
    def get_document_paths(
        project_config: ProjectConfig, path_to_dir: str
    ) -> List[str]:
        """The .typ files of the folder that are documents, not templates."""
        template_file_name_bases = get_template_file_name_bases(project_config)
        return sorted(
            path_
            for path_ in glob.glob(os.path.join(path_to_dir, "*.typ"))
            if os.path.splitext(os.path.basename(path_))[0]
            not in template_file_name_bases
        )

    @classmethod
    def build(
        cls, project_config: ProjectConfig, path_to_dir: str
    ) -> List[str]:
        """Compile the folder and return the paths of the PDF files."""
        deadline = time.monotonic() + TYPST_PDF_BUILD_TIMEOUT_SECONDS
        if (
            project_config.typst_pdf_command is not None
            or project_config.is_typst_template_external()
        ):
            cls._run(
                cls.get_command(project_config, path_to_dir),
                project_config,
                deadline,
            )
            paths_to_pdf = sorted(glob.glob(os.path.join(path_to_dir, "*.pdf")))
        else:
            paths_to_pdf = []
            for path_to_typ_ in cls.get_document_paths(
                project_config, path_to_dir
            ):
                path_to_pdf = os.path.splitext(path_to_typ_)[0] + ".pdf"
                cls._run(
                    [
                        "typst",
                        "compile",
                        "--root",
                        path_to_dir,
                        path_to_typ_,
                        path_to_pdf,
                    ],
                    project_config,
                    deadline,
                )
                paths_to_pdf.append(path_to_pdf)
        if len(paths_to_pdf) == 0:
            raise TypstPDFBuilderError(
                "Typst PDF: the build wrote no PDF file."
            )
        return paths_to_pdf

    @staticmethod
    def _run(
        command: List[str], project_config: ProjectConfig, deadline: float
    ) -> None:
        if shutil.which(command[0]) is None:
            hint = ""
            if command[0] == "typst":
                hint = (
                    " Install Typst (https://typst.app), or set "
                    "typst_pdf_command in the project config."
                )
            raise TypstPDFBuilderError(
                f"Typst PDF: the command '{command[0]}' is not installed or "
                f"is not on the PATH.{hint}"
            )
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=max(deadline - time.monotonic(), 1),
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
                    "<image name> <folder of its Dockerfile>', and set "
                    "typst_pdf_builder_image in the project config."
                )
            raise TypstPDFBuilderError(
                f"Typst PDF: the build failed with exit code "
                f"{result.returncode}:\n\n{output[-_OUTPUT_TAIL_LENGTH:]}"
                f"{hint}"
            )
