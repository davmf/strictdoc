"""
The SysML source editor of the workspace: the checks of the text and the
save, which refuses text that would break the tracker.
"""

import os
from typing import Dict

import pytest

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.sysml_workspace.sources import (
    check_source,
    read_source,
    save_source,
    source_hash,
)
from strictdoc.features.sysml_workspace.templates import WorkspaceEditError
from strictdoc.features.sysml_workspace.workspace import WorkspaceCache

FILES: Dict[str, str] = {
    "MODEL.sysml": """\
package 'MODEL' {
    @StrictDocWorkspace::Model { title = "Kettle"; }

    public import 'TRK-SYS';
}
""",
    "TRK-SYS/TRK-SYS.sysml": """\
package 'TRK-SYS' {
    @StrictDocWorkspace::Tracker { title = "System"; kind = "requirements"; prefix = "SYS"; }

    public import 'SYS-001'::*;
}
""",
    "TRK-SYS/SYS-001.sysml": """\
package 'SYS-001' {
    requirement <'SYS-001'> 'Boil time' {
    }
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


def test_01_valid_text_has_no_problems(cache):
    entry = cache.get().get("SYS-001")
    assert check_source(entry, read_source(entry)) == []


@pytest.mark.parametrize(
    "text, message, line",
    [
        (
            "package 'SYS-001' {\n    requirement x {\n}\n",
            "line 4, column 1: unexpected input",
            4,
        ),
        (
            "package 'SYS-002' {\n}\n",
            "the top-level package is 'SYS-002', expected 'SYS-001'",
            1,
        ),
        (
            "package 'SYS-001' {\n}\npackage 'X' {\n}\n",
            "one top-level package, found 2",
            None,
        ),
    ],
)
def test_02_problems_name_their_line(cache, text, message, line):
    problems = check_source(cache.get().get("SYS-001"), text)
    assert len(problems) == 1
    assert message in problems[0].message
    assert problems[0].line == line


def test_03_save_writes_the_text(cache):
    workspace = cache.get()
    entry = workspace.get("SYS-001")
    old_text = read_source(entry)
    new_text = old_text.replace("'Boil time'", "'Boil time, fast'")
    save_source(workspace, "SYS-001", new_text, source_hash(old_text))
    assert read_source(entry) == new_text
    assert cache.get().get("SYS-001").title == "Boil time, fast"


def test_04_a_file_changed_on_disk_is_not_overwritten(cache):
    workspace = cache.get()
    entry = workspace.get("SYS-001")
    old_text = read_source(entry)
    with open(entry.file_path, "w", encoding="utf-8") as file_:
        file_.write(old_text.replace("Boil", "Brew"))
    with pytest.raises(WorkspaceEditError) as exception_info:
        save_source(workspace, "SYS-001", old_text, source_hash(old_text))
    assert "changed on disk" in str(exception_info.value)
    assert "Brew" in read_source(entry)


def test_05_text_that_breaks_the_tracker_is_put_back(cache):
    workspace = cache.get()
    entry = workspace.get("TRK-SYS")
    old_text = read_source(entry)
    broken = old_text.replace("'SYS-001'::*;", "'SYS-404'::*;")
    with pytest.raises(WorkspaceEditError) as exception_info:
        save_source(workspace, "TRK-SYS", broken, source_hash(old_text))
    assert "the tracker TRK-SYS does not read" in str(exception_info.value)
    assert "'SYS-404' names no file" in str(exception_info.value)
    assert read_source(entry) == old_text
