import os
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = os.path.dirname(os.path.abspath(__file__))

DOCUMENT_MID = "2e8d2ad5e1d34a3a9c0f6c5f1d6b9a01"
NODE_MID = "7b1f0c3e9a2d4e5f8a6b0c1d2e3f4a5b"


def user_headers(groups: str) -> Dict[str, str]:
    return {
        "X-Forwarded-Email": "ada.lovelace@example.com",
        "X-Forwarded-Groups": groups,
    }


VIEWER = user_headers("staff")
EDITOR = user_headers("staff, sd-editors")
ADMIN = user_headers("sd-admins")


@pytest.fixture(scope="module")
def client() -> TestClient:
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=PATH_TO_THIS_TEST_FOLDER,
        output_path=os.path.join(PATH_TO_THIS_TEST_FOLDER, "output"),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
        auth_proxy_user_header="X-Forwarded-Email",
        auth_proxy_groups_header="X-Forwarded-Groups",
        auth_editor_group=["sd-editors"],
        auth_admin_group=["sd-admins"],
    )
    server_config.validate()
    project_config: ProjectConfig = ProjectConfig.default_config()
    project_config.integrate_server_config(server_config)
    return TestClient(create_app(project_config=project_config))


def test_01_viewer_can_read(client: TestClient):
    response = client.get("/27_roles/sample.html", headers=VIEWER)
    assert response.status_code == 200
    assert 'data-user-role="pending"' in response.text


def test_02_viewer_cannot_open_edit_forms(client: TestClient):
    response = client.get("/actions/project_index/new_document", headers=VIEWER)
    assert response.status_code == 403
    assert "viewer role" in response.text


def test_03_viewer_cannot_change_content(client: TestClient):
    response = client.post(
        "/actions/document/update_requirement", headers=VIEWER
    )
    assert response.status_code == 403
    response = client.delete(
        "/actions/document/delete_document",
        params={"document_mid": DOCUMENT_MID},
        headers=VIEWER,
    )
    assert response.status_code == 403


def test_04_viewer_can_show_full_node(client: TestClient):
    response = client.get(
        "/actions/show_full_node",
        params={"reference_mid": NODE_MID},
        headers=VIEWER,
    )
    assert response.status_code == 200


def test_05_editor_can_open_edit_forms(client: TestClient):
    response = client.get("/actions/project_index/new_document", headers=EDITOR)
    assert response.status_code == 200


def test_06_editor_cannot_edit_grammar(client: TestClient):
    response = client.get(
        "/actions/document/edit_grammar",
        params={"document_mid": DOCUMENT_MID},
        headers=EDITOR,
    )
    assert response.status_code == 403
    response = client.post("/actions/document/save_grammar", headers=EDITOR)
    assert response.status_code == 403


def test_07_admin_can_edit_grammar(client: TestClient):
    response = client.get(
        "/actions/document/edit_grammar",
        params={"document_mid": DOCUMENT_MID},
        headers=ADMIN,
    )
    assert response.status_code == 200


def test_08_badge_shows_role(client: TestClient):
    for headers_, role_ in (
        (VIEWER, "viewer"),
        (EDITOR, "editor"),
        (ADMIN, "admin"),
    ):
        response = client.get("/current_user", headers=headers_)
        assert f'data-user-role="{role_}"' in response.text


def test_09_group_names_must_match_exactly(client: TestClient):
    response = client.get(
        "/actions/project_index/new_document",
        headers=user_headers("SD-EDITORS, sd-editors-old"),
    )
    assert response.status_code == 403


def test_10_viewer_websocket_is_accepted(client: TestClient):
    with client.websocket_connect("/ws/1", headers=VIEWER) as websocket:
        websocket.send_text("ping")
