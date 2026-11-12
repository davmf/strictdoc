"""
Server endpoints of the SysML workspace screen.

- GET  /workspace?item=<ID>: the screen, with the entry <ID> selected (the
  model root without one).
- GET  /workspace/panes?item=<ID>: the middle and right panes of the entry,
  as JSON, for the script of the screen to swap in.
- POST /actions/sysml/workspace/new_item: create an item from a template.
- POST /actions/sysml/workspace/new_folder: create a folder.
- POST /actions/sysml/workspace/new_tracker: create a tracker.

The create actions are under /actions/, so proxy auth asks for the editor
role. They write the files while holding the global write lock, then
rebuild the traceability index (app.state.rebuild_and_notify_clients, set
by the main router), and redirect to the new entry.
"""

import os
from typing import Callable, Dict, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from starlette.responses import Response

from strictdoc import environment
from strictdoc.core.project_config import ProjectConfig
from strictdoc.export.html.html_templates import JinjaEnvironment
from strictdoc.export.html.jinja.assert_extension import AssertExtension
from strictdoc.features.sysml_workspace.templates import (
    WorkspaceEditError,
    create_folder,
    create_item,
    create_tracker,
)
from strictdoc.features.sysml_workspace.view_object import (
    WORKSPACE_URL,
    WorkspaceViewObject,
)
from strictdoc.features.sysml_workspace.workspace import (
    Workspace,
    WorkspaceCache,
)
from strictdoc.server.helpers.hierarchical_rw_lock_manager import (
    HierarchicalRWLockManager,
)
from strictdoc.server.helpers.proxy_auth import require_editor

HTTP_STATUS_SEE_OTHER = 303
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_UNPROCESSABLE_ENTITY = 422

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
NO_STORE = {"Cache-Control": "no-store"}


def create_sysml_workspace_router(
    *,
    project_config: ProjectConfig,
    lock_manager: HierarchicalRWLockManager,
) -> APIRouter:
    router = APIRouter()
    cache = WorkspaceCache(project_config)
    # The templates of the screen come first; they extend and include the
    # shared StrictDoc templates, which are left unchanged.
    jinja_environment = JinjaEnvironment(
        Environment(
            loader=FileSystemLoader(
                [TEMPLATES_DIR, *environment.get_path_to_html_templates()]
            ),
            undefined=StrictUndefined,
            extensions=[AssertExtension],
            autoescape=True,
        )
    )

    def read_workspace() -> Workspace:
        with lock_manager.acquire_global_read():
            return cache.get()

    def view_object_for(
        workspace: Workspace,
        item: Optional[str],
        error_message: Optional[str] = None,
        form_values: Optional[Dict[str, str]] = None,
    ) -> Optional[WorkspaceViewObject]:
        selected = (
            workspace.root
            if item is None or item == ""
            else workspace.get(item)
        )
        if selected is None:
            return None
        return WorkspaceViewObject(
            project_config=project_config,
            workspace=workspace,
            selected=selected,
            error_message=error_message,
            form_values=form_values,
        )

    def render_screen(
        view_object: WorkspaceViewObject, status_code: int = 200
    ) -> HTMLResponse:
        with lock_manager.acquire_global_read():
            content = view_object.render_screen(jinja_environment)
        return HTMLResponse(
            content=content, status_code=status_code, headers=NO_STORE
        )

    @router.get("/workspace", response_class=HTMLResponse)
    def get_workspace(item: Optional[str] = None) -> Response:
        view_object = view_object_for(read_workspace(), item)
        if view_object is None:
            return HTMLResponse(
                content=f"No entry '{item}' in the workspace.",
                status_code=HTTP_STATUS_NOT_FOUND,
            )
        return render_screen(view_object)

    @router.get("/workspace/panes", response_class=JSONResponse)
    def get_workspace_panes(item: Optional[str] = None) -> Response:
        view_object = view_object_for(read_workspace(), item)
        if view_object is None:
            return JSONResponse(
                {"error": f"No entry '{item}' in the workspace."},
                status_code=HTTP_STATUS_NOT_FOUND,
            )
        with lock_manager.acquire_global_read():
            panes = view_object.render_panes(jinja_environment)
        return JSONResponse(panes, headers=NO_STORE)

    def create(
        request: Request,
        parent_id: Optional[str],
        form_values: Dict[str, str],
        action: Callable[[Workspace], str],
    ) -> Response:
        with lock_manager.acquire_global_write():
            workspace = cache.get()
            try:
                new_id = action(workspace)
                create_error: Optional[str] = None
            except WorkspaceEditError as edit_error:
                create_error = str(edit_error)
            cache.invalidate()
        if create_error is not None:
            view_object = view_object_for(
                read_workspace(),
                parent_id,
                error_message=create_error,
                form_values=form_values,
            )
            assert view_object is not None
            return render_screen(
                view_object, status_code=HTTP_STATUS_UNPROCESSABLE_ENTITY
            )
        rebuild = getattr(request.app.state, "rebuild_and_notify_clients", None)
        if rebuild is not None:
            build_error: Optional[str] = rebuild()
            if build_error is not None:
                view_object = view_object_for(
                    read_workspace(),
                    new_id,
                    error_message=(
                        "The file was written, but the model has an error "
                        f"now:\n{build_error}"
                    ),
                )
                if view_object is not None:
                    return render_screen(
                        view_object,
                        status_code=HTTP_STATUS_UNPROCESSABLE_ENTITY,
                    )
        return RedirectResponse(
            url=f"{WORKSPACE_URL}?item={new_id}",
            status_code=HTTP_STATUS_SEE_OTHER,
        )

    @router.post(
        "/actions/sysml/workspace/new_item",
        dependencies=[Depends(require_editor)],
    )
    def post_new_item(
        request: Request,
        parent: str = Form(...),
        kind: str = Form(...),
        title: str = Form(""),
    ) -> Response:
        return create(
            request,
            parent,
            {"form": "item", "kind": kind, "title": title},
            lambda workspace_: create_item(workspace_, parent, kind, title),
        )

    @router.post(
        "/actions/sysml/workspace/new_folder",
        dependencies=[Depends(require_editor)],
    )
    def post_new_folder(
        request: Request,
        parent: str = Form(...),
        title: str = Form(""),
    ) -> Response:
        return create(
            request,
            parent,
            {"form": "folder", "title": title},
            lambda workspace_: create_folder(workspace_, parent, title),
        )

    @router.post(
        "/actions/sysml/workspace/new_tracker",
        dependencies=[Depends(require_editor)],
    )
    def post_new_tracker(
        request: Request,
        title: str = Form(""),
        kind: str = Form(""),
        prefix: str = Form(""),
    ) -> Response:
        return create(
            request,
            None,
            {"form": "tracker", "title": title, "kind": kind, "prefix": prefix},
            lambda workspace_: create_tracker(workspace_, title, kind, prefix),
        )

    return router
