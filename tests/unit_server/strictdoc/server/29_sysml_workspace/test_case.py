"""
The SysML workspace screen: the tree of the model, the panes of an entry and
the actions that create trackers, folders and items.
"""

import os
import re
import shutil

import pytest
from fastapi.testclient import TestClient

from strictdoc.backend.sysml.sysml_format import SysMLFormat
from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = os.path.dirname(os.path.abspath(__file__))

# Documents are served under the name of the input folder.
INPUT_FOLDER = "kettle"


@pytest.fixture(name="project")
def fixture_project(tmp_path) -> str:
    project_path = tmp_path / INPUT_FOLDER
    shutil.copytree(
        os.path.join(PATH_TO_THIS_TEST_FOLDER, "input"), project_path
    )
    return str(project_path)


@pytest.fixture(name="client")
def fixture_client(project) -> TestClient:
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=project,
        output_path=os.path.join(project, "output"),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
    )
    project_config = ProjectConfig(
        formats=[
            *ProjectConfig.default_formats(),
            SysMLFormat(tracker_layout=True),
        ],
    )
    project_config.integrate_server_config(server_config)
    return TestClient(create_app(project_config=project_config))


def _tree_ids(html: str):
    return re.findall(
        r'<li\s+class="sysml-ws-tree-entry"[^>]*data-entry-id="([^"]+)"', html
    )


def _read(project: str, path: str) -> str:
    with open(os.path.join(project, path), encoding="utf-8") as file_:
        return file_.read()


def test_01_the_tree_follows_the_model_root(client):
    response = client.get("/workspace")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    html = response.text
    assert _tree_ids(html) == [
        "MODEL",
        "TRK-STK",
        "STK-001",
        "TRK-SYS",
        "SYS-F-HEATING",
        "SYS-001",
        "SYS-002",
        "SYS-F-SAFETY",
        "SYS-010",
        "TRK-SC",
        "SC-001",
        "SC-002",
        "TRK-BEH",
        "BEH-001",
        "VIEW-001",
    ]
    # The model root is selected, with its trackers and the tracker form.
    assert 'data-testid="sysml-workspace-entry-title">Kettle<' in html
    assert 'data-testid="sysml-workspace-new-tracker"' in html
    assert "_static/plantuml/sysml/workspace.js" in html
    assert "_static/plantuml/sysml/sysml-diagrams.js" in html


def test_02_an_item_shows_its_fields_relations_and_diagram(client):
    response = client.get("/workspace", params={"item": "SYS-001"})
    assert response.status_code == 200
    html = response.text
    assert 'data-testid="sysml-workspace-entry-title">Boil time<' in html
    assert "The kettle shall boil 1 litre in at most 180 s." in html
    assert (
        'data-sysml-options="view=requirements focus=SYS-001 depth=1 orientation=horizontal '
        'links=/workspace?item={id}"'
    ) in html
    assert 'href="/UID/SYS-001"' in html
    side = html[html.index('data-testid="sysml-workspace-relations"') :]
    # SYS-001 depends on STK-001, and SC-001 satisfies it.
    assert re.search(
        r"Parent</span>\s*<a href=\"/workspace\?item=STK-001\"", side
    )
    assert re.search(
        r'<a href="/workspace\?item=SC-001"[^>]*>.*?SC-001</a>\s*'
        r'<span class="sysml-ws-role">Satisfies</span>',
        side,
        re.DOTALL,
    )
    # Outside a Git repository, the history says why it is empty.
    assert 'data-testid="sysml-workspace-history"' in html


def test_03_a_typing_links_to_the_item_of_its_definition(client):
    html = client.get("/workspace", params={"item": "SC-002"}).text
    side = html[html.index('data-testid="sysml-workspace-relations"') :]
    assert re.search(
        r'<a href="/workspace\?item=SC-001"[^>]*>.*?SC-001</a>\s*'
        r'<span class="sysml-ws-role">Typed by</span>',
        side,
        re.DOTALL,
    )


@pytest.mark.parametrize(
    "item, options",
    [
        ("BEH-001", "root=BEH-001"),
        ("VIEW-001", "diagram=VIEW-001 links=/workspace?item={id}"),
        ("TRK-SC", "view=definitions root=TRK-SC links=/workspace?item={id}"),
        (
            "SYS-F-HEATING",
            (
                "view=requirements root=SYS-F-HEATING depth=1 orientation=horizontal text=false "
                "links=/workspace?item={id}"
            ),
        ),
    ],
)
def test_04_the_diagram_of_each_kind_of_entry(client, item, options):
    html = client.get("/workspace", params={"item": item}).text
    assert f'data-sysml-options="{options}"' in html


def test_05_panes_are_json_for_the_script(client):
    response = client.get("/workspace/panes", params={"item": "TRK-SYS"})
    assert response.status_code == 200
    panes = response.json()
    assert panes["id"] == "TRK-SYS"
    assert "System requirements" in panes["main"]
    assert 'data-testid="sysml-workspace-contents"' in panes["main"]
    assert 'data-testid="sysml-workspace-relations"' in panes["side"]
    assert panes["title"].endswith("Workspace - TRK-SYS")


def test_06_an_unknown_entry_is_not_found(client):
    assert client.get("/workspace", params={"item": "NOPE"}).status_code == 404
    assert (
        client.get("/workspace/panes", params={"item": "NOPE"}).status_code
        == 404
    )


def test_07_a_new_requirement_is_written_included_and_indexed(client, project):
    response = client.post(
        "/actions/sysml/workspace/new_item",
        data={
            "parent": "SYS-F-SAFETY",
            "kind": "requirement",
            "title": "Lid lock",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/workspace?item=SYS-011"
    assert _read(project, "TRK-SYS/SYS-011.sysml") == (
        "package 'SYS-011' {\n"
        "    private import ScalarValues::*;\n"
        "    private import 'TRK-STK'::*;\n"
        "\n"
        "    requirement <'SYS-011'> 'Lid lock' {\n"
        "    }\n"
        "}\n"
    )
    assert "    public import 'SYS-011'::*;\n" in _read(
        project, "TRK-SYS/SYS-F-SAFETY.sysml"
    )
    html = client.get("/workspace", params={"item": "SYS-011"}).text
    assert 'data-testid="sysml-workspace-entry-title">Lid lock<' in html
    # The traceability index was rebuilt: the document screen knows it.
    response = client.get("/UID/SYS-011", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].endswith("TRK-SYS.html#SYS-011")


def test_08_a_new_state_machine_and_folder(client, project):
    response = client.post(
        "/actions/sysml/workspace/new_folder",
        data={"parent": "TRK-BEH", "title": "Lid"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/workspace?item=BEH-F-LID"
    response = client.post(
        "/actions/sysml/workspace/new_item",
        data={
            "parent": "BEH-F-LID",
            "kind": "statemachine",
            "title": "Lid control",
        },
        follow_redirects=False,
    )
    assert response.headers["location"] == "/workspace?item=BEH-002"
    text = _read(project, "TRK-BEH/BEH-002.sysml")
    assert "    private import StateMachineProfile::*;\n" in text
    assert "    part 'Lid control' : StateMachine {\n" in text
    html = client.get("/workspace", params={"item": "BEH-002"}).text
    assert 'data-sysml-options="root=BEH-002"' in html
    assert _tree_ids(html)[-3:] == ["VIEW-001", "BEH-F-LID", "BEH-002"]


def test_09_a_new_tracker_is_included_by_the_model_root(client, project):
    response = client.post(
        "/actions/sysml/workspace/new_tracker",
        data={"title": "Verification", "kind": "test cases", "prefix": "VER"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/workspace?item=TRK-VER"
    assert _read(project, "TRK-VER/TRK-VER.sysml") == (
        "package 'TRK-VER' {\n"
        '    @StrictDocWorkspace::Tracker { title = "Verification"; '
        'kind = "test cases"; prefix = "VER"; }\n'
        "}\n"
    )
    assert "    public import 'TRK-VER';\n" in _read(project, "MODEL.sysml")
    response = client.post(
        "/actions/sysml/workspace/new_item",
        data={
            "parent": "TRK-VER",
            "kind": "testcase",
            "title": "Boil time test",
        },
        follow_redirects=False,
    )
    assert response.headers["location"] == "/workspace?item=VER-001"
    html = client.get("/workspace", params={"item": "VER-001"}).text
    assert "Test case" in html


@pytest.mark.parametrize(
    "url, data, message",
    [
        (
            "/actions/sysml/workspace/new_item",
            {"parent": "SYS-F-SAFETY", "kind": "statemachine", "title": "X"},
            "cannot hold an item of the kind &#39;statemachine&#39;",
        ),
        (
            "/actions/sysml/workspace/new_item",
            {"parent": "SYS-F-SAFETY", "kind": "requirement", "title": " "},
            "The title is empty.",
        ),
        (
            "/actions/sysml/workspace/new_tracker",
            {"title": "Again", "kind": "requirements", "prefix": "SYS"},
            "already uses the prefix",
        ),
        (
            "/actions/sysml/workspace/new_tracker",
            {"title": "Bad", "kind": "requirements", "prefix": "low"},
            "A prefix is upper-case letters",
        ),
    ],
)
def test_10_a_bad_request_shows_the_form_again(
    client, project, url, data, message
):
    files_before = sorted(
        os.path.join(directory_, name_)
        for directory_, _, names_ in os.walk(project)
        for name_ in names_
        if name_.endswith(".sysml")
    )
    response = client.post(url, data=data, follow_redirects=False)
    assert response.status_code == 422
    assert 'data-testid="sysml-workspace-error"' in response.text
    assert message in response.text
    # The page is shown at the POST address: its relative links resolve
    # from the server root.
    assert '<base href="/"/>' in response.text
    files_after = sorted(
        os.path.join(directory_, name_)
        for directory_, _, names_ in os.walk(project)
        for name_ in names_
        if name_.endswith(".sysml")
    )
    assert files_after == files_before


def test_11_a_tracker_document_links_to_the_workspace(client):
    html = client.get(f"/{INPUT_FOLDER}/TRK-SYS/TRK-SYS.html").text
    assert '<a href="/workspace?item=TRK-SYS">Open in workspace</a>' in html


def test_12_with_proxy_auth_a_viewer_reads_but_does_not_create(project):
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=project,
        output_path=os.path.join(project, "output"),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
        auth_proxy_user_header="X-Forwarded-Email",
        auth_proxy_groups_header="X-Forwarded-Groups",
        auth_editor_group=["sd-editors"],
    )
    server_config.validate()
    project_config = ProjectConfig(
        formats=[
            *ProjectConfig.default_formats(),
            SysMLFormat(tracker_layout=True),
        ],
    )
    project_config.integrate_server_config(server_config)
    client = TestClient(create_app(project_config=project_config))
    viewer = {
        "X-Forwarded-Email": "viewer@example.com",
        "X-Forwarded-Groups": "staff",
    }
    assert client.get("/workspace", headers=viewer).status_code == 200
    assert (
        client.get(
            "/workspace/panes", params={"item": "SYS-001"}, headers=viewer
        ).status_code
        == 200
    )
    assert client.get("/sysml/model_files", headers=viewer).status_code == 200
    response = client.post(
        "/actions/sysml/workspace/new_folder",
        data={"parent": "TRK-BEH", "title": "Lid"},
        headers=viewer,
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert not os.path.exists(
        os.path.join(project, "TRK-BEH", "BEH-F-LID.sysml")
    )


VIEW_FORM = {
    "item": "VIEW-001",
    "title": "Heating, all transitions",
    "description": "",
    "exposes": "'BEH-001'::top::heating::**",
    "options": "transitions=all",
    "plantuml": "note right of ramp : checked",
}


def test_13_save_as_view_creates_a_view_of_the_entry(client, project):
    html = client.get("/workspace", params={"item": "BEH-001"}).text
    assert 'data-testid="sysml-workspace-save-as-view-form"' in html
    response = client.post(
        "/actions/sysml/workspace/new_view",
        data={"source": "BEH-001", "tracker": "TRK-BEH", "title": "Whole"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/workspace?item=BEH-002"
    assert "    expose 'BEH-001';\n" in _read(project, "TRK-BEH/BEH-002.sysml")
    html = client.get("/workspace", params={"item": "BEH-002"}).text
    assert 'data-testid="sysml-workspace-view-editor"' in html
    assert 'data-sysml-options="diagram=BEH-002 ' in html
    # The state machine lists its views.
    side = client.get("/workspace/panes", params={"item": "BEH-001"}).json()[
        "side"
    ]
    assert 'data-entry-id="BEH-002"' in side
    assert 'data-entry-id="VIEW-001"' in side


def test_14_the_preview_text_is_not_saved(client, project):
    before = _read(project, "TRK-BEH/VIEW-001.sysml")
    response = client.post("/workspace/view_source", data=VIEW_FORM)
    assert response.status_code == 200
    preview = response.json()
    assert preview["name"] == "TRK-BEH/VIEW-001.sysml"
    assert 'options = "transitions=all";' in preview["text"]
    assert _read(project, "TRK-BEH/VIEW-001.sysml") == before
    response = client.post(
        "/workspace/view_source", data={**VIEW_FORM, "exposes": "x; y"}
    )
    assert response.status_code == 422
    assert "is not an expose target" in response.json()["error"]


def test_15_save_view_writes_the_view_file(client, project):
    response = client.post(
        "/actions/sysml/workspace/save_view",
        data=VIEW_FORM,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/workspace?item=VIEW-001"
    assert _read(project, "TRK-BEH/VIEW-001.sysml") == (
        "package 'VIEW-001' {\n"
        "    private import 'TRK-BEH'::*;\n"
        "\n"
        "    view <'VIEW-001'> 'Heating, all transitions' {\n"
        "        @StrictDocWorkspace::DiagramView {\n"
        '            options = "transitions=all";\n'
        '            plantuml = "note right of ramp : checked";\n'
        "        }\n"
        "        expose 'BEH-001'::top::heating::**;\n"
        "    }\n"
        "}\n"
    )
    html = client.get("/workspace", params={"item": "VIEW-001"}).text
    assert (
        'data-testid="sysml-workspace-entry-title">Heating, all transitions<'
    ) in html


def test_16_a_bad_view_keeps_what_was_typed(client, project):
    before = _read(project, "TRK-BEH/VIEW-001.sysml")
    response = client.post(
        "/actions/sysml/workspace/save_view",
        data={**VIEW_FORM, "description": "a */ b"},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert "cannot contain" in response.text
    assert ">a */ b</textarea>" in response.text
    assert 'value="transitions=all"' in response.text
    assert _read(project, "TRK-BEH/VIEW-001.sysml") == before


def _base_hash(html: str) -> str:
    match_ = re.search(r'name="base_hash" value="([0-9a-f]+)"', html)
    assert match_ is not None
    return match_.group(1)


def test_17_the_source_editor_saves_the_file(client, project):
    html = client.get(
        "/workspace", params={"item": "SYS-002", "edit": "source"}
    ).text
    assert 'data-testid="sysml-workspace-source-form"' in html
    assert "_static/plantuml/sysml/workspace.js" in html
    text = _read(project, "TRK-SYS/SYS-002.sysml")
    new_text = text.replace("'Keep warm'", "'Keep the water warm'")
    response = client.post(
        "/actions/sysml/workspace/save_source",
        data={
            "item": "SYS-002",
            "text": new_text,
            "base_hash": _base_hash(html),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/workspace?item=SYS-002"
    assert _read(project, "TRK-SYS/SYS-002.sysml") == new_text
    html = client.get("/workspace", params={"item": "SYS-002"}).text
    assert (
        'data-testid="sysml-workspace-entry-title">Keep the water warm<'
    ) in html


def test_18_check_source_names_the_problem(client, project):
    response = client.post(
        "/workspace/check_source",
        data={
            "item": "SYS-002",
            "text": "package 'SYS-002' {\n  part x {\n}\n",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "TRK-SYS/SYS-002.sysml"
    assert result["problems"][0]["line"] == 4
    response = client.post(
        "/workspace/check_source",
        data={
            "item": "SYS-002",
            "text": _read(project, "TRK-SYS/SYS-002.sysml"),
        },
    )
    assert response.json()["problems"] == []


def test_19_a_refused_save_keeps_the_typed_text(client, project):
    html = client.get(
        "/workspace", params={"item": "SYS-002", "edit": "source"}
    ).text
    before = _read(project, "TRK-SYS/SYS-002.sysml")
    response = client.post(
        "/actions/sysml/workspace/save_source",
        data={
            "item": "SYS-002",
            "text": "package 'SYS-999' {\n}\n",
            "base_hash": _base_hash(html),
        },
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert "expected &#39;SYS-002&#39;" in response.text
    assert "package &#39;SYS-999&#39; {\n}\n</textarea>" in response.text
    assert _read(project, "TRK-SYS/SYS-002.sysml") == before
