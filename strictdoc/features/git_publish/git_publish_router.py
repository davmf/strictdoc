"""
@relation(SDOC-SRS-208, SDOC-SRS-209, SDOC-SRS-210, SDOC-SRS-211, scope=file)
"""

import os
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

from fastapi import APIRouter, FastAPI
from starlette.responses import HTMLResponse, RedirectResponse, Response

from strictdoc.core.project_config import ProjectConfig
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.export.html.html_templates import (
    HTMLTemplates,
    JinjaEnvironment,
)
from strictdoc.features.git_publish.git_publish_screen_view_object import (
    GitPublishScreenViewObject,
)
from strictdoc.features.git_publish.git_publish_service import (
    DiscardResult,
    GitPublishService,
    UnpublishedChange,
)
from strictdoc.server.helpers.hierarchical_rw_lock_manager import (
    HierarchicalRWLockManager,
)

HTTP_STATUS_FORBIDDEN = 403
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_PRECONDITION_FAILED = 412
HTTP_STATUS_UNPROCESSABLE_ENTITY = 422

TURBO_STREAM_HEADERS = {"Content-Type": "text/vnd.turbo-stream.html"}


def create_git_publish_router(
    project_config: ProjectConfig,
    *,
    app: FastAPI,
    lock_manager: HierarchicalRWLockManager,
) -> APIRouter:
    router = APIRouter()

    html_templates = HTMLTemplates.create(
        project_config=project_config,
        enable_caching=False,
        strictdoc_last_update=datetime.today(),
    )

    git_publish_service = GitPublishService.create(project_config)

    # Serializes discard (and later publish) within this server process, so
    # that two browser tabs cannot run them at the same time. A thread lock,
    # not a file lock: fcntl is not available on Windows.
    git_publish_lock = threading.Lock()

    def env() -> JinjaEnvironment:
        return html_templates.jinja_environment()

    def get_document_titles_by_full_path() -> Dict[str, str]:
        get_traceability_index: Callable[[], TraceabilityIndex] = (
            app.state.get_traceability_index
        )
        document_titles_by_full_path: Dict[str, str] = {}
        with lock_manager.acquire_global_read():
            traceability_index = get_traceability_index()
            assert traceability_index.document_tree is not None
            for document_ in traceability_index.document_tree.document_list:
                if document_.meta is None:
                    continue
                document_titles_by_full_path[
                    os.path.realpath(document_.meta.input_doc_full_path)
                ] = document_.title
        return document_titles_by_full_path

    def create_view_object(
        unpublished_changes: List[UnpublishedChange],
    ) -> GitPublishScreenViewObject:
        return GitPublishScreenViewObject(
            project_config=project_config,
            is_available=git_publish_service.is_available(),
            is_write_allowed=git_publish_service.is_write_allowed(),
            unpublished_changes=unpublished_changes,
        )

    def feature_not_activated_response() -> Response:
        return Response(
            content=(
                "The GIT_PUBLISH feature is not activated "
                "in the project config."
            ),
            status_code=HTTP_STATUS_PRECONDITION_FAILED,
        )

    @router.get("/git_publish/badge", response_class=Response)
    def get_git_publish_badge() -> Response:
        if not project_config.is_activated_git_publish():
            return feature_not_activated_response()
        # Count from "git status" alone. The badge is requested on every page
        # load, so it must not run the changelog engine.
        view_object = create_view_object(
            git_publish_service.get_unpublished_changes({})
        )
        output = env().render_template_as_markup(
            "features/git_publish/badge_content.jinja",
            view_object=view_object,
        )
        return HTMLResponse(
            content=output,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/git_publish", response_class=Response)
    def get_git_publish_screen() -> Response:
        if not project_config.is_activated_git_publish():
            return feature_not_activated_response()
        view_object = create_view_object(
            git_publish_service.get_unpublished_changes(
                get_document_titles_by_full_path()
            )
        )
        output = view_object.render_screen(env())
        return HTMLResponse(
            content=output,
            headers={"Cache-Control": "no-store"},
        )

    @router.delete("/git_publish/discard", response_class=Response)
    def discard_unpublished_change(
        path: str, confirmed: bool = False
    ) -> Response:
        if not project_config.is_activated_git_publish():
            return feature_not_activated_response()
        if not git_publish_service.is_available():
            return Response(
                content=GitPublishScreenViewObject.UNAVAILABLE_MESSAGE,
                status_code=HTTP_STATUS_PRECONDITION_FAILED,
            )
        if not git_publish_service.is_write_allowed():
            return Response(
                content=GitPublishScreenViewObject.WRITE_NOT_ALLOWED_MESSAGE,
                status_code=HTTP_STATUS_FORBIDDEN,
            )

        with git_publish_lock:
            # Validate the path against the current state on disk. This also
            # guarantees that the path is a managed file.
            unpublished_change: Optional[UnpublishedChange] = (
                git_publish_service.find_unpublished_change(
                    path, get_document_titles_by_full_path()
                )
            )
            if unpublished_change is None:
                return Response(
                    content=(
                        "This file has no unpublished changes. "
                        "Reload the page to see the current list."
                    ),
                    status_code=HTTP_STATUS_NOT_FOUND,
                )

            if not confirmed:
                output = env().render_template_as_markup(
                    "features/git_publish/stream_confirm_discard.jinja",
                    unpublished_change=unpublished_change,
                    discard_url=GitPublishScreenViewObject.get_discard_url(
                        unpublished_change
                    ),
                )
                return HTMLResponse(
                    content=output, headers=TURBO_STREAM_HEADERS
                )

            discard_result = discard_with_watcher_inhibited(unpublished_change)

        if not discard_result.is_success():
            output = env().render_template_as_markup(
                "features/git_publish/stream_discard_failed.jinja",
                discard_result=discard_result,
            )
            return HTMLResponse(
                content=output,
                status_code=HTTP_STATUS_UNPROCESSABLE_ENTITY,
                headers=TURBO_STREAM_HEADERS,
            )

        return RedirectResponse("/git_publish", status_code=303)

    def discard_with_watcher_inhibited(
        unpublished_change: UnpublishedChange,
    ) -> DiscardResult:
        # Suppress the watcher's own rebuild for this file. The rebuild below
        # covers it, so the index is rebuilt once and not twice.
        document_watcher = getattr(app.state, "document_watcher", None)
        if document_watcher is not None and (
            git_publish_service.is_document_file(unpublished_change.full_path)
        ):
            document_watcher.inhibit_next_change(unpublished_change.full_path)

        with lock_manager.acquire_global_write():
            discard_result = git_publish_service.discard_change(
                unpublished_change
            )

        # The rebuild runs whether or not the watcher is enabled. It takes
        # the global write lock itself, so it must run after the lock above
        # is released.
        rebuild_after_feature_file_change: Callable[[], Optional[str]] = (
            app.state.rebuild_after_feature_file_change
        )
        rebuild_after_feature_file_change()
        return discard_result

    return router
