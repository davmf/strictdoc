"""
Provide the workspace, the selected entry and the forms to the templates of
the workspace screen.
"""

import os
import posixpath
import re
from typing import Dict, List, Optional
from urllib.parse import quote

from markupsafe import Markup

from strictdoc import __version__
from strictdoc.backend.rst.rst_to_html_fragment_writer import (
    RstToHtmlFragmentWriter,
)
from strictdoc.backend.sysml.diagram import diagram_options
from strictdoc.core.project_config import ProjectConfig
from strictdoc.export.html.html_templates import JinjaEnvironment
from strictdoc.export.html.renderers.link_renderer import LinkRenderer
from strictdoc.features.sysml_workspace.history import (
    FileHistory,
    file_history,
)
from strictdoc.features.sysml_workspace.templates import (
    TRACKER_KINDS,
    ItemTemplate,
    templates_for,
)
from strictdoc.features.sysml_workspace.workspace import (
    ENTRY_FOLDER,
    ENTRY_ITEM,
    ENTRY_MODEL,
    ENTRY_TRACKER,
    Workspace,
    WorkspaceEntry,
)
from strictdoc.helpers.file_system import file_open_read_utf8

WORKSPACE_URL = "/workspace"
ITEM_LINK_PATTERN = WORKSPACE_URL + "?item={id}"
# The letter of the icon of each kind of entry.
ICON_LETTERS: Dict[str, str] = {
    "model": "M",
    "tracker": "T",
    "folder": "F",
    "requirement": "R",
    "testcase": "V",
    "part": "P",
    "partdef": "P",
    "action": "A",
    "calc": "C",
    "analysis": "A",
    "view": "D",
    "statemachine": "S",
    "sequence": "Q",
    "timing": "W",
    "activity": "A",
    "interconnect": "I",
    "pcba": "B",
    "cots": "B",
    "element": "E",
}
# The tables of the members of a design element.
MEMBER_FIELDS = ("DETAILS", "MEMBERS")
# Multiline fields are RST; one-line fields are shown as text.
_RST_MARKERS = ("\n", "**", "``", ".. ", "`")
# A relative URL in rendered RST (an image in `_assets`...).
_RELATIVE_URL_PATTERN = re.compile(
    r'(\s(?:src|href)=")(?![a-zA-Z][a-zA-Z0-9+.-]*:|/|#)'
)


class WorkspaceViewObject:
    def __init__(
        self,
        *,
        project_config: ProjectConfig,
        workspace: Workspace,
        selected: WorkspaceEntry,
        error_message: Optional[str] = None,
        form_values: Optional[Dict[str, str]] = None,
    ) -> None:
        self.project_config: ProjectConfig = project_config
        self.workspace: Workspace = workspace
        self.selected: WorkspaceEntry = selected
        self.error_message: Optional[str] = error_message
        self.form_values: Dict[str, str] = (
            form_values if form_values is not None else {}
        )
        self.link_renderer: LinkRenderer = LinkRenderer(
            root_path="", static_path=project_config.dir_for_sdoc_assets
        )
        self.is_running_on_server: bool = project_config.is_running_on_server
        self.strictdoc_version: str = __version__
        self.tracker_kinds = TRACKER_KINDS
        self._expanded = {id(entry_) for entry_ in selected.ancestors()}
        self._expanded.add(id(workspace.root))
        self._expanded.add(id(selected))
        self._rst_writer: Optional[RstToHtmlFragmentWriter] = None

    # The base layout (base.jinja.html, nav.jinja.html) needs these.

    def get_document_level(self) -> int:
        return 0

    def render_static_url(self, url: str) -> Markup:
        return Markup(self.link_renderer.render_static_url(url))

    def render_url(self, url: str) -> Markup:
        return Markup(self.link_renderer.render_url(url))

    # The screen.

    def render_screen(self, jinja_environment: JinjaEnvironment) -> Markup:
        return jinja_environment.render_template_as_markup(
            "features/sysml_workspace/index.jinja", view_object=self
        )

    def render_panes(
        self, jinja_environment: JinjaEnvironment
    ) -> Dict[str, str]:
        """The middle and right panes, for the script to swap in."""
        return {
            "id": self.selected.entry_id,
            "title": self.page_title(),
            "main": str(
                jinja_environment.render_template_as_markup(
                    "features/sysml_workspace/main.jinja", view_object=self
                )
            ),
            "side": str(
                jinja_environment.render_template_as_markup(
                    "features/sysml_workspace/side.jinja", view_object=self
                )
            ),
        }

    def page_title(self) -> str:
        return (
            f"{self.project_config.project_title} - Workspace - "
            f"{self.selected.entry_id}"
        )

    def is_expanded(self, entry: WorkspaceEntry) -> bool:
        return id(entry) in self._expanded

    def is_selected(self, entry: WorkspaceEntry) -> bool:
        return entry is self.selected

    def entry_url(self, entry: WorkspaceEntry) -> str:
        return WORKSPACE_URL + "?item=" + quote(entry.entry_id, safe="")

    def icon_letter(self, entry: WorkspaceEntry) -> str:
        return ICON_LETTERS.get(entry.icon, "E")

    def document_url(self, entry: WorkspaceEntry) -> Optional[str]:
        """Where the entry is edited: its node on the document screen."""
        if entry.entry_type == ENTRY_ITEM and entry.node is not None:
            return "/UID/" + quote(entry.entry_id, safe="")
        if entry.tracker is not None:
            return entry.tracker.document_url
        return None

    def is_model(self, entry: WorkspaceEntry) -> bool:
        return entry.entry_type == ENTRY_MODEL

    def is_container(self, entry: WorkspaceEntry) -> bool:
        return entry.entry_type in (ENTRY_TRACKER, ENTRY_FOLDER)

    def is_item(self, entry: WorkspaceEntry) -> bool:
        return entry.entry_type == ENTRY_ITEM

    def diagram_options(self, entry: WorkspaceEntry) -> Optional[str]:
        """
        The !include_sysml options of the diagram of the entry: the profile
        diagram of a profile root, the saved diagram of a view, the trace
        diagram of another item, the overview of a tracker or a folder.
        """
        links = f"links={ITEM_LINK_PATTERN}"
        if entry.entry_type == ENTRY_ITEM:
            if entry.icon == "view":
                return f"diagram={entry.entry_id} {links}"
            if entry.profile_type is not None:
                return f"root={entry.entry_id}"
            return f"view=requirements focus={entry.entry_id} depth=1 {links}"
        if entry.entry_type in (ENTRY_TRACKER, ENTRY_FOLDER):
            items = entry.items()
            tracker_entry = entry.tracker
            is_design = tracker_entry is not None and tracker_entry.is_design()
            # The overview of design items draws their definitions: without
            # one, it would be empty.
            if len(items) == 0 or (
                is_design
                and not any(
                    item_.node is not None
                    and item_.node.node_type.endswith("_DEF")
                    for item_ in items
                )
            ):
                return None
            options = diagram_options(entry.entry_id, is_design)
            if is_design:
                options += f" {links}"
            return options.replace("links=/?a={id}", links)
        return None

    def fields(
        self, entry: WorkspaceEntry, members: bool = False
    ) -> List[Dict[str, object]]:
        """
        The fields of the entry: the statement and the attributes, or with
        members=True, the tables of the members of a design element, shown
        after the diagram.
        """
        result: List[Dict[str, object]] = []
        base_url = self._document_directory_url(entry)
        for name_, text_ in entry.fields():
            if (name_ in MEMBER_FIELDS) != members:
                continue
            result.append(
                {
                    "name": name_,
                    "label": name_.replace("_", " ").capitalize(),
                    "value": self._render_field(text_, base_url),
                    "is_block": any(
                        marker_ in text_ for marker_ in _RST_MARKERS
                    ),
                }
            )
        return result

    def source_text(self, entry: WorkspaceEntry) -> Optional[str]:
        if entry.file_path is None or not os.path.isfile(entry.file_path):
            return None
        with file_open_read_utf8(entry.file_path) as file_:
            return file_.read()

    def history(self, entry: WorkspaceEntry) -> Optional[FileHistory]:
        if entry.file_path is None:
            return None
        return file_history(entry.file_path)

    def item_templates(self, entry: WorkspaceEntry) -> List[ItemTemplate]:
        return templates_for(entry)

    def form_value(self, name: str, default: str = "") -> str:
        return self.form_values.get(name, default)

    def _render_field(self, text: str, base_url: Optional[str]) -> Markup:
        if not any(marker_ in text for marker_ in _RST_MARKERS):
            return Markup.escape(text)
        if self._rst_writer is None:
            self._rst_writer = RstToHtmlFragmentWriter(
                project_config=self.project_config, context_document=None
            )
        html = str(self._rst_writer.write(text))
        if base_url is not None:
            # The fields are written for the document screen: a relative
            # URL is relative to the folder of the tracker's document.
            html = _RELATIVE_URL_PATTERN.sub(
                lambda match_: match_.group(1) + base_url, html
            )
        return Markup(html)

    @staticmethod
    def _document_directory_url(entry: WorkspaceEntry) -> Optional[str]:
        if entry.tracker is None or entry.tracker.document_url is None:
            return None
        return posixpath.dirname(entry.tracker.document_url) + "/"
