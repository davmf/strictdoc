"""
The model of the SysML workspace screen: the tree from the model root, the
kinds of the items, the relations between items, and the cache.
"""

import os
from typing import Dict

import pytest

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.sysml_workspace.workspace import WorkspaceCache

FILES: Dict[str, str] = {
    "MODEL.sysml": """\
package 'MODEL' {
    @StrictDocWorkspace::Model { title = "Kettle"; }

    public import 'TRK-SYS';
    public import 'TRK-BEH';
}
""",
    "TRK-SYS/TRK-SYS.sysml": """\
package 'TRK-SYS' {
    @StrictDocWorkspace::Tracker { title = "System"; kind = "requirements"; prefix = "SYS"; }

    public import 'SYS-F-HEATING'::*;
}
""",
    "TRK-SYS/SYS-F-HEATING.sysml": """\
package 'SYS-F-HEATING' {
    @StrictDocWorkspace::Folder { title = "Heating"; }

    public import 'SYS-001'::*;
}
""",
    "TRK-SYS/SYS-001.sysml": """\
package 'SYS-001' {
    requirement <'SYS-001'> 'Boil time' {
        doc /*
         * The kettle shall boil 1 litre in at most 180 s.
         */
    }
}
""",
    "TRK-BEH/TRK-BEH.sysml": """\
package 'TRK-BEH' {
    @StrictDocWorkspace::Tracker { title = "Behaviour"; kind = "behaviour"; prefix = "BEH"; }

    public import 'BEH-001'::*;
    public import 'BEH-002'::*;
}
""",
    "TRK-BEH/BEH-001.sysml": """\
package 'BEH-001' {
    private import StateMachineProfile::*;
    private import 'TRK-SYS'::*;

    part kettle : StateMachine {
        part :>> top : Region {
            part idle : State;
        }
    }

    satisfy 'SYS-001' by kettle;
}
""",
    "TRK-BEH/BEH-002.sysml": """\
package 'BEH-002' {
    part def Heater;
}
""",
    # A tracker that the model root does not include comes last.
    "TRK-ZZZ/TRK-ZZZ.sysml": """\
package 'TRK-ZZZ' {
    @StrictDocWorkspace::Tracker { title = "Loose"; kind = "design"; prefix = "ZZZ"; }
}
""",
}


@pytest.fixture(name="project")
def fixture_project(tmp_path) -> str:
    for path_, text_ in FILES.items():
        full_path = tmp_path / path_
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(text_, encoding="utf-8")
    return str(tmp_path)


def _cache(project: str) -> WorkspaceCache:
    project_config = ProjectConfig.default_config()
    project_config.input_paths = [project]
    project_config.output_dir = os.path.join(project, "output")
    return WorkspaceCache(project_config)


def _ids(entry):
    return [entry.entry_id] + [
        id_ for child_ in entry.children for id_ in _ids(child_)
    ]


def test_01_the_tree_follows_the_includes(project):
    workspace = _cache(project).get()
    assert workspace.root.title == "Kettle"
    assert _ids(workspace.root) == [
        "MODEL",
        "TRK-SYS",
        "SYS-F-HEATING",
        "SYS-001",
        "TRK-BEH",
        "BEH-001",
        "BEH-002",
        "TRK-ZZZ",
    ]
    assert workspace.errors == []
    assert (
        workspace.get("TRK-SYS").document_url
        == "/" + os.path.basename(project) + "/TRK-SYS/TRK-SYS.html"
    )


def test_02_items_have_a_kind(project):
    workspace = _cache(project).get()
    kinds = {
        id_: (entry_.icon, entry_.kind_label, entry_.profile_type)
        for id_, entry_ in workspace.entries.items()
    }
    assert kinds["SYS-001"] == ("requirement", "Requirement", None)
    assert kinds["BEH-001"] == ("statemachine", "State machine", "StateMachine")
    assert kinds["BEH-002"] == ("partdef", "Part definition", None)
    assert kinds["SYS-F-HEATING"] == ("folder", "Folder", None)
    assert workspace.get("SYS-001").title == "Boil time"
    assert [name_ for name_, _ in workspace.get("SYS-001").fields()] == [
        "STATEMENT"
    ]


def test_03_relations_go_both_ways(project):
    workspace = _cache(project).get()
    state_machine = workspace.get("BEH-001")
    requirement = workspace.get("SYS-001")
    assert [
        (relation_.role, relation_.entry.entry_id)
        for relation_ in state_machine.outgoing
    ] == [("Satisfies", "SYS-001")]
    assert [
        (relation_.role, relation_.entry.entry_id)
        for relation_ in requirement.incoming
    ] == [("Satisfies", "BEH-001")]


def test_04_a_broken_tracker_is_an_error_not_a_crash(project):
    os.remove(os.path.join(project, "TRK-BEH", "BEH-002.sysml"))
    workspace = _cache(project).get()
    assert "TRK-BEH" not in workspace.entries
    assert len(workspace.errors) == 1
    assert "'BEH-002' names no file" in workspace.errors[0]
    assert _ids(workspace.root)[-1] == "TRK-ZZZ"


def test_05_the_cache_reads_again_after_a_change(project):
    cache = _cache(project)
    first = cache.get()
    assert cache.get() is first
    path = os.path.join(project, "TRK-SYS", "SYS-001.sysml")
    with open(path, encoding="utf-8") as file_:
        text = file_.read()
    with open(path, "w", encoding="utf-8") as file_:
        file_.write(text.replace("'Boil time'", "'Boil time, fast'"))
    second = cache.get()
    assert second is not first
    assert second.get("SYS-001").title == "Boil time, fast"
    # A new file in a folder of the model is seen too.
    with open(
        os.path.join(project, "TRK-BEH", "BEH-003.sysml"), "w", encoding="utf-8"
    ) as file_:
        file_.write("package 'BEH-003' {\n    part def Lid;\n}\n")
    assert cache.get() is not second
