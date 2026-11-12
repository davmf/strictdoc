"""
Server endpoint of the SysML diagrams.

- GET /sysml/model_files: the text of every SysML file of the project, for
  the browser to draw the diagrams of SysML documents (see
  strictdoc/backend/sysml/diagram.py). The route is not under /actions/, so
  that with proxy auth a viewer can read it: it only shows content.

The router also holds the routes of the SysML workspace screen
(strictdoc/features/sysml_workspace/router.py).
"""

from typing import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.sysml_diagrams.model_files import find_model_files
from strictdoc.features.sysml_workspace.router import (
    create_sysml_workspace_router,
)
from strictdoc.server.helpers.hierarchical_rw_lock_manager import (
    HierarchicalRWLockManager,
)


def create_sysml_diagrams_router(
    *,
    project_config: ProjectConfig,
    lock_manager: HierarchicalRWLockManager,
) -> APIRouter:
    def read_lock() -> Iterator[None]:
        # The files are not read while a save writes them.
        with lock_manager.acquire_global_read():
            yield

    router = APIRouter()

    @router.get("/sysml/model_files", dependencies=[Depends(read_lock)])
    def get_model_files() -> JSONResponse:
        return JSONResponse(
            {"files": find_model_files(project_config)},
            headers={"Cache-Control": "no-store"},
        )

    router.include_router(
        create_sysml_workspace_router(
            project_config=project_config, lock_manager=lock_manager
        )
    )
    return router
