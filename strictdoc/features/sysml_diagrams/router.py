"""
Server endpoint of the SysML diagrams.

- GET /actions/sysml/model_files: the text of every SysML file of the
  project, for the browser to draw the diagrams of SysML documents (see
  strictdoc/backend/sysml/diagram.py).
"""

import os
from typing import Dict, Iterator, List

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from strictdoc.core.file_system.file_tree import File, FileFinder
from strictdoc.core.project_config import ProjectConfig
from strictdoc.helpers.file_system import file_open_read_utf8
from strictdoc.server.helpers.hierarchical_rw_lock_manager import (
    HierarchicalRWLockManager,
)

SYSML_EXTENSION = ".sysml"


def create_sysml_diagrams_router(
    *,
    project_config: ProjectConfig,
    lock_manager: HierarchicalRWLockManager,
) -> APIRouter:
    def read_lock() -> Iterator[None]:
        # The files are not read while a save writes them.
        with lock_manager.acquire_global_read():
            yield

    router = APIRouter(dependencies=[Depends(read_lock)])

    @router.get("/actions/sysml/model_files")
    def get_model_files() -> JSONResponse:
        return JSONResponse(
            {"files": find_model_files(project_config)},
            headers={"Cache-Control": "no-store"},
        )

    return router


def find_model_files(project_config: ProjectConfig) -> List[Dict[str, str]]:
    """
    Every .sysml file of the input paths, libraries included, with the
    include and exclude paths of the project. Each file is
    {"name": <path relative to its input path>, "text": <content>}.
    """
    files: List[Dict[str, str]] = []
    for input_path_ in project_config.input_paths or []:
        if os.path.isfile(input_path_):
            if input_path_.endswith(SYSML_EXTENSION):
                files.append(
                    _model_file(
                        os.path.abspath(input_path_),
                        os.path.basename(input_path_),
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
        for _, file_, _ in file_tree.iterate():
            assert isinstance(file_, File)
            files.append(
                _model_file(file_.full_path, file_.rel_path.relative_path_posix)
            )
    return files


def _model_file(full_path: str, name: str) -> Dict[str, str]:
    with file_open_read_utf8(full_path) as file_:
        return {"name": name, "text": file_.read()}
