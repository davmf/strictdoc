"""
Saved views of the SysML workspace: the view file, read and written back,
the checks of the view editor, "Save as view" and the expose suggestions.
"""

import os
from typing import Dict

import pytest

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.sysml_workspace.templates import WorkspaceEditError
from strictdoc.features.sysml_workspace.views import (
    ViewFields,
    checked_view_fields,
    create_view,
    expose_suggestions,
    initial_view_fields,
    read_view,
    save_view,
    view_text,
)
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

    public import 'SYS-001'::*;
}
""",
    "TRK-SYS/SYS-001.sysml": """\
package 'SYS-001' {
    requirement <'SYS-001'> 'Boil time' {
    }
}
""",
    "TRK-BEH/TRK-BEH.sysml": """\
package 'TRK-BEH' {
    @StrictDocWorkspace::Tracker { title = "Behaviour"; kind = "behaviour"; prefix = "BEH"; }

    public import 'BEH-001'::*;
    public import 'BEH-002'::*;
    public import 'BEH-003'::*;
}
""",
    "TRK-BEH/BEH-001.sysml": """\
package 'BEH-001' {
    private import StateMachineProfile::*;

    part kettle : StateMachine {
        part :>> top : Region {
            part idle : State;
            part heating : CompositeState {
                part :>> regions : Region {
                    part ramp : State;
                }
            }
        }
    }
}
""",
    "TRK-BEH/BEH-002.sysml": """\
package 'BEH-002' {
    private import 'TRK-BEH'::*;

    view <'BEH-002'> 'Heating only' {
        doc /*
         * The heating state.
         */
        @StrictDocWorkspace::DiagramView {
            options = "transitions=primary";
            plantuml = "note right of ramp : \\"ok\\"\\nskinparam shadowing false";
        }
        expose 'BEH-001'::top::heating::**;
    }
}
""",
    "TRK-BEH/BEH-003.sysml": """\
package 'BEH-003' {
    part def Heater;
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


def test_01_a_view_file_reads_into_the_editor_fields(cache):
    fields = read_view(cache.get().get("BEH-002"))
    assert fields == ViewFields(
        title="Heating only",
        description="The heating state.",
        exposes=["'BEH-001'::top::heating::**"],
        options="transitions=primary",
        plantuml='note right of ramp : "ok"\nskinparam shadowing false',
        imports=["private import 'TRK-BEH'::*;"],
    )


def test_02_the_fields_write_the_same_file(cache):
    fields = read_view(cache.get().get("BEH-002"))
    assert view_text("BEH-002", fields) == FILES["TRK-BEH/BEH-002.sysml"]


def test_03_the_editor_checks_and_imports(cache):
    workspace = cache.get()
    tracker = workspace.get("TRK-BEH")
    fields = checked_view_fields(
        workspace,
        tracker,
        " Traces ",
        "",
        "expose 'SYS-001';\n\n'BEH-001'::top\n",
        'depth=2  title="A b"',
        "",
    )
    assert fields.title == "Traces"
    assert fields.exposes == ["'SYS-001'", "'BEH-001'::top"]
    # The view's tracker, then the trackers of what it exposes.
    assert fields.imports == [
        "private import 'TRK-BEH'::*;",
        "private import 'TRK-SYS'::*;",
    ]
    assert 'options = "depth=2 title=\\"A b\\"";' in view_text("X", fields)


@pytest.mark.parametrize(
    "description, exposes, options, message",
    [
        ("a */ b", "", "", "cannot contain '*/'"),
        ("", "'BEH-001'; part x", "", "is not an expose target"),
        ("", "'BEH-001' { }", "", "is not an expose target"),
        ("", "", "a=1\nb=2", "one line"),
    ],
)
def test_04_the_editor_refuses_what_would_break_the_file(
    cache, description, exposes, options, message
):
    workspace = cache.get()
    with pytest.raises(WorkspaceEditError) as exception_info:
        checked_view_fields(
            workspace,
            workspace.get("TRK-BEH"),
            "T",
            description,
            exposes,
            options,
            "",
        )
    assert message in str(exception_info.value)


def test_05_save_as_view_starts_from_the_diagram_of_the_entry(cache):
    workspace = cache.get()
    assert initial_view_fields(workspace.get("BEH-001")).exposes == [
        "'BEH-001'"
    ]
    requirement = initial_view_fields(workspace.get("SYS-001"))
    assert (requirement.exposes, requirement.options) == (
        ["'SYS-001'"],
        "depth=1",
    )
    part_def = initial_view_fields(workspace.get("BEH-003"))
    assert (part_def.exposes, part_def.options) == (
        [],
        "view=requirements focus=BEH-003 depth=1",
    )
    tracker = initial_view_fields(workspace.get("TRK-SYS"))
    assert tracker.exposes == ["'TRK-SYS'::**"]
    # A view is no source of a view.
    assert initial_view_fields(workspace.get("BEH-002")) is None


def test_06_create_and_save_a_view(cache):
    view_id = create_view(cache.get(), "SYS-001", "TRK-BEH", "")
    assert view_id == "BEH-004"
    workspace = cache.get()
    view = workspace.get("BEH-004")
    assert view is not None and view.icon == "view"
    assert view.title == "Boil time traces"
    # The view shows what it exposes.
    assert [
        (relation_.role, relation_.entry.entry_id)
        for relation_ in view.outgoing
    ] == [("Shows", "SYS-001")]
    fields = read_view(view)
    fields.options = "depth=2"
    save_view(workspace, "BEH-004", fields)
    assert (
        'options = "depth=2";' in open(view.file_path, encoding="utf-8").read()
    )
    with pytest.raises(WorkspaceEditError):
        create_view(workspace, "SYS-001", "TRK-SYS", "")
    with pytest.raises(WorkspaceEditError):
        save_view(workspace, "SYS-001", fields)


def test_07_suggestions_include_the_states_of_a_state_machine(cache):
    suggestions = expose_suggestions(cache.get())
    assert suggestions[:2] == ["'TRK-SYS'::**", "'SYS-001'"]
    assert "'BEH-001'::top::heating::regions::ramp" in suggestions
    assert "'BEH-001'::top::idle" in suggestions
    assert "'BEH-002'" not in suggestions
