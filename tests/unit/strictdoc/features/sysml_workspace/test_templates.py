"""
New trackers, folders and items of the SysML workspace: the text of the new
files, their IDs and the includes added to their parents.
"""

import os
from typing import Dict

import pytest

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.sysml_workspace.templates import (
    ITEM_TEMPLATES,
    WorkspaceEditError,
    add_include,
    create_folder,
    create_item,
    create_tracker,
    templates_for,
)
from strictdoc.features.sysml_workspace.workspace import WorkspaceCache

FILES: Dict[str, str] = {
    "model/MODEL.sysml": """\
package 'MODEL' {
    @StrictDocWorkspace::Model { title = "Kettle"; }

    public import 'TRK-BEH';
}
""",
    "model/TRK-BEH/TRK-BEH.sysml": """\
package 'TRK-BEH' {
    @StrictDocWorkspace::Tracker { title = "Behaviour"; kind = "behaviour"; prefix = "BEH"; }
    doc /*
     * Behaviour of the kettle.
     */
}
""",
}


@pytest.fixture(name="cache")
def fixture_cache(tmp_path) -> WorkspaceCache:
    for path_, text_ in FILES.items():
        full_path = tmp_path / path_
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(text_, encoding="utf-8")
    project_config = ProjectConfig.default_config()
    project_config.input_paths = [str(tmp_path)]
    project_config.output_dir = os.path.join(str(tmp_path), "output")
    return WorkspaceCache(project_config)


def _read(cache: WorkspaceCache, path: str) -> str:
    assert cache.project_config.input_paths is not None
    with open(
        os.path.join(cache.project_config.input_paths[0], path),
        encoding="utf-8",
    ) as file_:
        return file_.read()


def test_01_the_first_include_goes_before_the_closing_brace(cache):
    assert create_item(cache.get(), "TRK-BEH", "part", "Lid sensor") == (
        "BEH-001"
    )
    assert _read(cache, "model/TRK-BEH/TRK-BEH.sysml") == (
        "package 'TRK-BEH' {\n"
        '    @StrictDocWorkspace::Tracker { title = "Behaviour"; '
        'kind = "behaviour"; prefix = "BEH"; }\n'
        "    doc /*\n"
        "     * Behaviour of the kettle.\n"
        "     */\n"
        "\n"
        "    public import 'BEH-001'::*;\n"
        "}\n"
    )
    assert _read(cache, "model/TRK-BEH/BEH-001.sysml") == (
        "package 'BEH-001' {\n"
        "    private import 'TRK-BEH'::*;\n"
        "\n"
        "    part 'Lid sensor' {\n"
        "    }\n"
        "}\n"
    )


def test_02_ids_follow_the_highest_number(cache):
    root = cache.project_config.input_paths[0]
    with open(
        os.path.join(root, "model/TRK-BEH/BEH-007.sysml"), "w", encoding="utf-8"
    ) as file_:
        file_.write("package 'BEH-007' {\n    part def One;\n}\n")
    add_include(
        os.path.join(root, "model/TRK-BEH/TRK-BEH.sysml"),
        "    public import 'BEH-007'::*;",
    )
    assert create_item(cache.get(), "TRK-BEH", "partdef", "Two") == "BEH-008"
    # A second include goes after the last one.
    assert (
        "    public import 'BEH-007'::*;\n    public import 'BEH-008'::*;\n"
        in _read(cache, "model/TRK-BEH/TRK-BEH.sysml")
    )


@pytest.mark.parametrize("template", ITEM_TEMPLATES, ids=lambda t: t.key)
def test_03_every_template_reads_back_as_its_kind(tmp_path, template):
    files = dict(FILES)
    if template.for_requirements:
        files["model/TRK-BEH/TRK-BEH.sysml"] = files[
            "model/TRK-BEH/TRK-BEH.sysml"
        ].replace('kind = "behaviour"', 'kind = "requirements"')
    for path_, text_ in files.items():
        full_path = tmp_path / path_
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(text_, encoding="utf-8")
    project_config = ProjectConfig.default_config()
    project_config.input_paths = [str(tmp_path)]
    project_config.output_dir = os.path.join(str(tmp_path), "output")
    cache = WorkspaceCache(project_config)
    item_id = create_item(cache.get(), "TRK-BEH", template.key, "Pump head")
    workspace = cache.get()
    assert workspace.errors == []
    item = workspace.get(item_id)
    assert item is not None
    assert item.icon == template.icon
    assert item.title in ("Pump head", "'Pump head'")


def test_04_templates_follow_the_kind_of_the_tracker(cache):
    workspace = cache.get()
    keys = [
        template_.key for template_ in templates_for(workspace.get("TRK-BEH"))
    ]
    assert "requirement" not in keys
    assert "statemachine" in keys
    with pytest.raises(WorkspaceEditError):
        create_item(workspace, "TRK-BEH", "requirement", "No")
    with pytest.raises(WorkspaceEditError):
        create_item(workspace, "MODEL", "part", "No")


def test_05_folders_get_a_slug_id(cache):
    assert create_folder(cache.get(), "TRK-BEH", "Lid & lock") == (
        "BEH-F-LID-LOCK"
    )
    cache.invalidate()
    assert create_folder(cache.get(), "TRK-BEH", "Lid & lock") == (
        "BEH-F-LID-LOCK-2"
    )
    assert _read(cache, "model/TRK-BEH/BEH-F-LID-LOCK.sysml") == (
        "package 'BEH-F-LID-LOCK' {\n"
        '    @StrictDocWorkspace::Folder { title = "Lid & lock"; }\n'
        "}\n"
    )


def test_06_a_tracker_gets_a_folder_next_to_the_model_root(cache):
    assert create_tracker(cache.get(), 'The "SW"', "design", "SW") == "TRK-SW"
    assert _read(cache, "model/TRK-SW/TRK-SW.sysml") == (
        "package 'TRK-SW' {\n"
        '    @StrictDocWorkspace::Tracker { title = "The \\"SW\\""; '
        'kind = "design"; prefix = "SW"; }\n'
        "}\n"
    )
    assert "    public import 'TRK-BEH';\n    public import 'TRK-SW';\n" in (
        _read(cache, "model/MODEL.sysml")
    )
    cache.invalidate()
    assert cache.get().get("TRK-SW").title == 'The "SW"'


@pytest.mark.parametrize(
    "title, kind, prefix, message",
    [
        ("A", "design", "BEH", "already uses the prefix"),
        ("A", "design", "sw", "A prefix is upper-case"),
        ("A", "other", "SW", "Unknown tracker kind"),
        ("", "design", "SW", "The title is empty."),
        ("A\nB", "design", "SW", "The title is one line."),
    ],
)
def test_07_tracker_errors(cache, title, kind, prefix, message):
    with pytest.raises(WorkspaceEditError) as exception_info:
        create_tracker(cache.get(), title, kind, prefix)
    assert message in str(exception_info.value)


def test_08_add_include_without_closing_brace_is_an_error(tmp_path):
    path = tmp_path / "X.sysml"
    path.write_text("package 'X' {", encoding="utf-8")
    with pytest.raises(WorkspaceEditError):
        add_include(str(path), "    public import 'Y'::*;")
