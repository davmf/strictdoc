"""
The SysML files of a project: every .sysml file of the input paths, with
the include and exclude paths of the project.
"""

import os
import posixpath
from dataclasses import dataclass
from typing import Dict, List

from strictdoc.core.file_system.file_tree import File, FileFinder
from strictdoc.core.project_config import ProjectConfig
from strictdoc.helpers.file_system import file_open_read_utf8

SYSML_EXTENSION = ".sysml"


@dataclass(frozen=True)
class ModelFile:
    full_path: str
    # The path relative to its input path.
    name: str
    # The folder that the documents of its input path are served under.
    mount_folder: str

    def document_url(self) -> str:
        """The URL of the document screen of the file, if it is one."""
        return "/" + "/".join(
            part_
            for part_ in (
                self.mount_folder,
                posixpath.splitext(self.name)[0] + ".html",
            )
            if len(part_) > 0
        )


def find_model_files(project_config: ProjectConfig) -> List[Dict[str, str]]:
    """
    Every .sysml file of the input paths, libraries included, with the
    include and exclude paths of the project. Each file is
    {"name": <path relative to its input path>, "text": <content>}.
    """
    files: List[Dict[str, str]] = []
    for model_file_ in find_model_file_paths(project_config):
        with file_open_read_utf8(model_file_.full_path) as file_:
            files.append({"name": model_file_.name, "text": file_.read()})
    return files


def find_model_file_paths(project_config: ProjectConfig) -> List[ModelFile]:
    """
    Every .sysml file of the input paths, with the include and exclude
    paths of the project.
    """
    paths: List[ModelFile] = []
    for input_path_ in project_config.input_paths or []:
        if os.path.isfile(input_path_):
            if input_path_.endswith(SYSML_EXTENSION):
                paths.append(
                    ModelFile(
                        full_path=os.path.abspath(input_path_),
                        name=os.path.basename(input_path_),
                        mount_folder="",
                    )
                )
            continue
        root_path = os.path.abspath(input_path_.rstrip("/"))
        file_tree = FileFinder.find_files_with_extensions(
            root_path=root_path,
            ignored_dirs=[project_config.output_dir]
            if project_config.output_dir is not None
            else [],
            extensions=[SYSML_EXTENSION],
            include_paths=project_config.include_doc_paths,
            exclude_paths=project_config.exclude_doc_paths,
        )
        for _, file_, mount_folder_ in file_tree.iterate():
            assert isinstance(file_, File)
            paths.append(
                ModelFile(
                    full_path=file_.full_path,
                    name=file_.rel_path.relative_path_posix,
                    mount_folder=mount_folder_,
                )
            )
    return paths
