"""
Server endpoints of the project actions feature.

- GET  /project_actions: the run screen.
- POST /project_actions/run: start an action from a submitted form.
- POST /project_actions/cancel: stop the running action.
- GET  /project_actions/stream: the output of a run as server-sent events.
- GET  /project_actions/output/{run_id}/{path}: an output file of a run.
"""

import json
from pathlib import Path
from typing import Dict, Iterator, Optional

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from starlette.responses import Response, StreamingResponse

from strictdoc.core.project_config import ProjectConfig
from strictdoc.export.html.html_templates import NormalHTMLTemplates
from strictdoc.features.project_actions.project_action import (
    ProjectAction,
    ProjectActionValidationError,
    build_argv,
)
from strictdoc.features.project_actions.runner import (
    ProjectActionBusyError,
    ProjectActionRunner,
)
from strictdoc.features.project_actions.view_object import (
    ProjectActionsScreenViewObject,
)

HTTP_STATUS_SEE_OTHER = 303
HTTP_STATUS_FORBIDDEN = 403
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_CONFLICT = 409
HTTP_STATUS_PRECONDITION_FAILED = 412
HTTP_STATUS_UNPROCESSABLE_ENTITY = 422

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

# The stream sends a comment line when there is no output for this long, so
# that the server notices a closed connection.
STREAM_KEEPALIVE_SECONDS = 15.0


def create_project_actions_router(
    *, project_config: ProjectConfig, app: FastAPI
) -> APIRouter:
    router = APIRouter()
    html_templates = NormalHTMLTemplates()

    def rebuild() -> Optional[str]:
        rebuild_and_notify_clients = getattr(
            app.state, "rebuild_and_notify_clients", None
        )
        if rebuild_and_notify_clients is None:
            return None
        build_error: Optional[str] = rebuild_and_notify_clients()
        return build_error

    project_root = (
        project_config.input_paths[0]
        if project_config.input_paths is not None
        and len(project_config.input_paths) > 0
        else "."
    )
    runner = ProjectActionRunner(project_root=project_root, on_finished=rebuild)

    def runs_allowed() -> bool:
        return (
            project_config.allow_remote_project_actions
            or project_config.server_host in LOOPBACK_HOSTS
        )

    def not_activated_response() -> Response:
        return Response(
            content=(
                "The Project actions feature is not activated in the "
                "project config."
            ),
            status_code=HTTP_STATUS_PRECONDITION_FAILED,
        )

    def render_screen(
        *,
        selected_action: Optional[ProjectAction],
        bound_element: Optional[str],
        form_values: Optional[Dict[str, str]] = None,
        form_errors: Optional[Dict[str, str]] = None,
        error_message: Optional[str] = None,
        status_code: int = 200,
    ) -> Response:
        view_object = ProjectActionsScreenViewObject(
            project_config=project_config,
            last_run=runner.last_run,
            selected_action=selected_action,
            bound_element=bound_element,
            form_values=form_values,
            form_errors=form_errors,
            error_message=error_message,
            runs_allowed=runs_allowed(),
        )
        return Response(
            content=view_object.render_screen(
                html_templates.jinja_environment()
            ),
            status_code=status_code,
            media_type="text/html",
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/project_actions", response_class=Response)
    def get_project_actions(
        action: Optional[str] = None, element: Optional[str] = None
    ) -> Response:
        if not project_config.is_activated_project_actions():
            return not_activated_response()
        selected_action = (
            project_config.get_project_action(action)
            if action is not None
            else None
        )
        bound_element = (
            element
            if selected_action is not None
            and selected_action.sysml_binding is not None
            else None
        )
        return render_screen(
            selected_action=selected_action, bound_element=bound_element
        )

    @router.post("/project_actions/run", response_class=Response)
    async def post_project_actions_run(request: Request) -> Response:
        if not project_config.is_activated_project_actions():
            return not_activated_response()
        form_data = await request.form()
        form_values: Dict[str, str] = {
            key_: value_
            for key_, value_ in form_data.items()
            if isinstance(value_, str)
        }
        handle = form_values.get("action", "")
        action = project_config.get_project_action(handle)
        if action is None:
            return render_screen(
                selected_action=None,
                bound_element=None,
                error_message=f"Unknown action: {handle}.",
                status_code=HTTP_STATUS_NOT_FOUND,
            )
        bound_element = (
            form_values.get("element")
            if action.sysml_binding is not None
            else None
        )
        if not runs_allowed():
            return render_screen(
                selected_action=action,
                bound_element=bound_element,
                form_values=form_values,
                error_message="Running actions is disabled on this host.",
                status_code=HTTP_STATUS_FORBIDDEN,
            )
        if bound_element is not None and action.sysml_binding is not None:
            form_values[action.sysml_binding.parameter] = bound_element
        try:
            argv = build_argv(action, form_values)
        except ProjectActionValidationError as validation_error_:
            return render_screen(
                selected_action=action,
                bound_element=bound_element,
                form_values=form_values,
                form_errors=validation_error_.errors,
                status_code=HTTP_STATUS_UNPROCESSABLE_ENTITY,
            )
        try:
            runner.start(action, argv)
        except ProjectActionBusyError as busy_error_:
            return render_screen(
                selected_action=action,
                bound_element=bound_element,
                form_values=form_values,
                error_message=str(busy_error_),
                status_code=HTTP_STATUS_CONFLICT,
            )
        return RedirectResponse(
            url="/project_actions", status_code=HTTP_STATUS_SEE_OTHER
        )

    @router.post("/project_actions/cancel", response_class=Response)
    def post_project_actions_cancel() -> Response:
        if not project_config.is_activated_project_actions():
            return not_activated_response()
        runner.cancel()
        return RedirectResponse(
            url="/project_actions", status_code=HTTP_STATUS_SEE_OTHER
        )

    @router.get("/project_actions/stream", response_class=Response)
    def get_project_actions_stream(run_id: int, offset: int = 0) -> Response:
        if not project_config.is_activated_project_actions():
            return not_activated_response()

        def stream_events() -> Iterator[str]:
            next_offset = offset
            while True:
                lines, next_offset, is_finished = runner.wait_for_lines(
                    run_id, next_offset, STREAM_KEEPALIVE_SECONDS
                )
                for line_ in lines:
                    yield f"data: {json.dumps(line_)}\n\n"
                if is_finished:
                    yield "event: finished\ndata: {}\n\n"
                    return
                if len(lines) == 0:
                    yield ": keepalive\n\n"

        return StreamingResponse(
            stream_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store"},
        )

    @router.get(
        "/project_actions/output/{run_id}/{relative_path:path}",
        response_class=Response,
    )
    def get_project_actions_output(run_id: int, relative_path: str) -> Response:
        if not project_config.is_activated_project_actions():
            return not_activated_response()
        run = runner.last_run
        # Only files that the last run changed and that match the declared
        # outputs are served.
        if (
            run is None
            or run.run_id != run_id
            or not runner.is_output_file(relative_path)
        ):
            return Response(status_code=HTTP_STATUS_NOT_FOUND)
        path_to_file = Path(runner.project_root, relative_path)
        return FileResponse(path_to_file, headers={"Cache-Control": "no-store"})

    return router
