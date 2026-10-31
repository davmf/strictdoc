import os
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = os.path.dirname(os.path.abspath(__file__))

USER_HEADERS = {
    "X-Forwarded-Email": "ada.lovelace@example.com",
    "X-Forwarded-Preferred-Username": "Ada Lovelace",
}


def create_client(auth_proxy_user_header: Optional[str]) -> TestClient:
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=PATH_TO_THIS_TEST_FOLDER,
        # Rendered pages are cached in the output folder, and the nav bar
        # differs between the two modes.
        output_path=os.path.join(
            PATH_TO_THIS_TEST_FOLDER,
            "output",
            "with_auth" if auth_proxy_user_header is not None else "no_auth",
        ),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
        auth_proxy_user_header=auth_proxy_user_header,
        auth_proxy_email_header="X-Forwarded-Email"
        if auth_proxy_user_header is not None
        else None,
        auth_proxy_name_header="X-Forwarded-Preferred-Username"
        if auth_proxy_user_header is not None
        else None,
    )
    server_config.validate()
    project_config: ProjectConfig = ProjectConfig.default_config()
    project_config.integrate_server_config(server_config)
    return TestClient(create_app(project_config=project_config))


@pytest.fixture(scope="module")
def client() -> TestClient:
    return create_client("X-Forwarded-Email")


def test_01_request_without_user_is_rejected(client: TestClient):
    response = client.get("/26_proxy_auth/sample.html")
    assert response.status_code == 401
    assert "Sign-in required" in response.text


def test_02_request_with_user_is_served(client: TestClient):
    response = client.get("/26_proxy_auth/sample.html", headers=USER_HEADERS)
    assert response.status_code == 200
    assert 'id="nav_current_user"' in response.text


def test_03_healthz_does_not_need_user(client: TestClient):
    response = client.get("/healthz")
    assert response.status_code == 200


def test_04_current_user_badge(client: TestClient):
    response = client.get("/current_user", headers=USER_HEADERS)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert 'data-testid="nav-current-user"' in response.text
    assert ">AL<" in response.text
    assert (
        'title="Signed in as Ada Lovelace (ada.lovelace@example.com), viewer"'
        in response.text
    )


def test_05_badge_escapes_header_values(client: TestClient):
    response = client.get(
        "/current_user",
        headers={
            "X-Forwarded-Email": "x@example.com",
            "X-Forwarded-Preferred-Username": '"><script>alert(1)</script>',
        },
    )
    assert response.status_code == 200
    assert "<script>" not in response.text


def test_06_duplicated_user_header_is_rejected(client: TestClient):
    response = client.get(
        "/26_proxy_auth/sample.html",
        headers=[
            ("X-Forwarded-Email", "ada.lovelace@example.com"),
            ("X-Forwarded-Email", "mallory@example.com"),
        ],
    )
    assert response.status_code == 401


def test_07_websocket_without_user_is_rejected(client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/1"):
            pass
    assert exc_info.value.code == 1008


def test_08_websocket_with_user_is_accepted(client: TestClient):
    with client.websocket_connect("/ws/1", headers=USER_HEADERS) as websocket:
        websocket.send_text("ping")


def test_09_without_proxy_auth_nothing_changes():
    client = create_client(None)
    response = client.get("/26_proxy_auth/sample.html")
    assert response.status_code == 200
    assert 'id="nav_current_user"' not in response.text

    response = client.get("/current_user")
    assert response.status_code == 200
    assert response.text == ""
