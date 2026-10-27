"""
Provide the project actions and the last run to the run screen template.
"""

import os
import shlex
from dataclasses import dataclass
from typing import Dict, List, Optional

from markupsafe import Markup

from strictdoc import __version__
from strictdoc.core.project_config import ProjectConfig
from strictdoc.export.html.html_templates import JinjaEnvironment
from strictdoc.export.html.renderers.link_renderer import LinkRenderer
from strictdoc.features.project_actions.project_action import (
    ProjectAction,
    ProjectActionParameter,
)
from strictdoc.features.project_actions.runner import ProjectActionRun

IMAGE_EXTENSIONS = (".svg", ".png", ".jpg", ".jpeg", ".gif")
VIDEO_EXTENSIONS = (".mp4", ".webm")
HTML_EXTENSIONS = (".html", ".htm")


@dataclass
class ProjectActionsScreenViewObject:
    def __init__(
        self,
        *,
        project_config: ProjectConfig,
        last_run: Optional[ProjectActionRun],
        selected_action: Optional[ProjectAction],
        bound_element: Optional[str],
        form_values: Optional[Dict[str, str]] = None,
        form_errors: Optional[Dict[str, str]] = None,
        error_message: Optional[str] = None,
        runs_allowed: bool = True,
    ) -> None:
        self.project_config: ProjectConfig = project_config
        self.last_run: Optional[ProjectActionRun] = last_run
        self.selected_action: Optional[ProjectAction] = selected_action
        self.bound_element: Optional[str] = bound_element
        self.form_values: Dict[str, str] = (
            form_values if form_values is not None else {}
        )
        self.form_errors: Dict[str, str] = (
            form_errors if form_errors is not None else {}
        )
        self.error_message: Optional[str] = error_message
        self.runs_allowed: bool = runs_allowed
        self.link_renderer: LinkRenderer = LinkRenderer(
            root_path="", static_path=project_config.dir_for_sdoc_assets
        )
        self.is_running_on_server: bool = project_config.is_running_on_server
        self.strictdoc_version: str = __version__

    def get_document_level(self) -> int:
        return 0

    def render_screen(self, jinja_environment: JinjaEnvironment) -> Markup:
        return jinja_environment.render_template_as_markup(
            "features/project_actions/index.jinja",
            view_object=self,
        )

    def render_static_url(self, url: str) -> Markup:
        return Markup(self.link_renderer.render_static_url(url))

    def render_static_url_with_prefix(self, url: str) -> str:
        return self.link_renderer.render_static_url_with_prefix(url)

    def render_url(self, url: str) -> Markup:
        return Markup(self.link_renderer.render_url(url))

    def get_actions(self) -> List[ProjectAction]:
        """The selected action first, then the others in config order."""
        actions = list(self.project_config.project_actions)
        if self.selected_action is not None:
            actions.remove(self.selected_action)
            actions.insert(0, self.selected_action)
        return actions

    def is_run_in_progress(self) -> bool:
        return self.last_run is not None and not self.last_run.is_finished()

    def get_value(
        self, action: ProjectAction, parameter: ProjectActionParameter
    ) -> str:
        if self.is_bound_parameter(action, parameter):
            assert self.bound_element is not None
            return self.bound_element
        if (
            action is self.selected_action
            and parameter.name in self.form_values
        ):
            return self.form_values[parameter.name]
        return parameter.get_default_as_text()

    def get_error(
        self, action: ProjectAction, parameter: ProjectActionParameter
    ) -> Optional[str]:
        if action is not self.selected_action:
            return None
        return self.form_errors.get(parameter.name)

    def is_bound_parameter(
        self, action: ProjectAction, parameter: ProjectActionParameter
    ) -> bool:
        return (
            action is self.selected_action
            and self.bound_element is not None
            and action.sysml_binding is not None
            and action.sysml_binding.parameter == parameter.name
        )

    @staticmethod
    def render_command(argv: List[str]) -> str:
        return shlex.join(argv)

    @staticmethod
    def get_output_kind(relative_path: str) -> str:
        extension = os.path.splitext(relative_path)[1].lower()
        if extension in IMAGE_EXTENSIONS:
            return "image"
        if extension in VIDEO_EXTENSIONS:
            return "video"
        if extension in HTML_EXTENSIONS:
            return "html"
        return "file"

    @staticmethod
    def get_output_url(run: ProjectActionRun, relative_path: str) -> str:
        # The run id makes the URL change between runs, so that the browser
        # does not show a cached copy of an earlier output.
        return f"/project_actions/output/{run.run_id}/{relative_path}"
