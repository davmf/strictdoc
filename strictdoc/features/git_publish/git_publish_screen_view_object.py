"""
@relation(SDOC-SRS-208, SDOC-SRS-209, scope=file)
"""

from typing import List, Optional
from urllib.parse import quote

from markupsafe import Markup

from strictdoc import __version__
from strictdoc.core.project_config import ProjectConfig
from strictdoc.export.html.html_templates import JinjaEnvironment
from strictdoc.export.html.renderers.link_renderer import LinkRenderer
from strictdoc.features.git_publish.git_publish_service import (
    UnpublishedChange,
)


class GitPublishScreenViewObject:
    UNAVAILABLE_MESSAGE = (
        "Publishing is unavailable: this project is not in a Git repository"
    )
    WRITE_NOT_ALLOWED_MESSAGE = (
        "Discarding changes is disabled because this server accepts "
        "connections from other computers. Run the server on 127.0.0.1, "
        "::1 or localhost to enable it."
    )

    def __init__(
        self,
        *,
        project_config: ProjectConfig,
        is_available: bool,
        is_write_allowed: bool,
        unpublished_changes: List[UnpublishedChange],
    ) -> None:
        self.project_config: ProjectConfig = project_config
        self.is_available: bool = is_available
        self.is_write_allowed: bool = is_write_allowed
        self.unpublished_changes: List[UnpublishedChange] = unpublished_changes
        self.link_renderer: LinkRenderer = LinkRenderer(
            root_path="", static_path=project_config.dir_for_sdoc_assets
        )
        self.is_running_on_server: bool = project_config.is_running_on_server
        self.strictdoc_version: str = __version__

    def get_badge_text(self) -> str:
        unpublished_change_count = len(self.unpublished_changes)
        if unpublished_change_count == 0:
            return "All changes published"
        if unpublished_change_count == 1:
            return "1 unpublished change"
        return f"{unpublished_change_count} unpublished changes"

    def get_changelog_url(self) -> Optional[str]:
        """
        The changelog view belongs to the DIFF feature. Without it, there is
        no link.
        """

        if not self.project_config.is_activated_diff():
            return None
        return "/diff?left_revision=HEAD&right_revision=HEAD%2B&tab=changelog"

    @staticmethod
    def get_discard_url(unpublished_change: UnpublishedChange) -> str:
        return "/git_publish/discard?path=" + quote(
            unpublished_change.path, safe=""
        )

    def get_document_level(self) -> int:
        return 0

    def render_screen(self, jinja_environment: JinjaEnvironment) -> Markup:
        return jinja_environment.render_template_as_markup(
            "features/git_publish/index.jinja", view_object=self
        )

    def render_url(self, url: str) -> Markup:
        return Markup(self.link_renderer.render_url(url))

    def render_static_url(self, url: str) -> Markup:
        return Markup(self.link_renderer.render_static_url(url))

    def render_static_url_with_prefix(self, url: str) -> str:
        return self.link_renderer.render_static_url_with_prefix(url)
