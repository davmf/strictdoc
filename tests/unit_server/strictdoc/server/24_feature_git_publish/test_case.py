"""
@relation(SDOC-SRS-208, SDOC-SRS-210, SDOC-SRS-212, SDOC-SRS-214, scope=file)
"""

import os
import subprocess

from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig
from strictdoc.server.app import create_app

DOCUMENT_CONTENT = """\
[DOCUMENT]
TITLE: Requirements

[REQUIREMENT]
UID: REQ-1
STATEMENT: The system shall work.
"""


def _git(path_to_repository: str, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=path_to_repository,
        capture_output=True,
        check=True,
    )


def _create_repository(path_to_repository: str) -> None:
    _git(path_to_repository, "init", "--quiet")
    _git(path_to_repository, "config", "user.name", "Test User")
    _git(path_to_repository, "config", "user.email", "test@example.com")
    with open(
        os.path.join(path_to_repository, "requirements.sdoc"),
        "w",
        encoding="utf8",
    ) as file_:
        file_.write(DOCUMENT_CONTENT)
    with open(
        os.path.join(path_to_repository, "notes.txt"), "w", encoding="utf8"
    ) as file_:
        file_.write("Notes\n")
    _git(path_to_repository, "add", "-A")
    _git(path_to_repository, "commit", "--quiet", "-m", "Initial commit")


def _create_project_config(path_to_repository: str, host: str) -> ProjectConfig:
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=path_to_repository,
        output_path=os.path.join(path_to_repository, "output"),
        config=None,
        reload=False,
        host=host,
        port=8001,
    )
    project_config = ProjectConfig(project_features=["GIT_PUBLISH"])
    project_config.integrate_server_config(server_config)
    return project_config


def _modify_file(path_to_file: str) -> None:
    with open(path_to_file, "a", encoding="utf8") as file_:
        file_.write("\n")


def test_badge_screen_and_discard(tmp_path):
    path_to_repository = str(tmp_path)
    _create_repository(path_to_repository)
    path_to_document = os.path.join(path_to_repository, "requirements.sdoc")
    path_to_notes = os.path.join(path_to_repository, "notes.txt")

    client = TestClient(
        create_app(
            project_config=_create_project_config(
                path_to_repository, "127.0.0.1"
            )
        )
    )

    response = client.get("/git_publish/badge")
    assert response.status_code == 200
    assert "All changes published" in response.text

    _modify_file(path_to_document)
    _modify_file(path_to_notes)

    response = client.get("/git_publish/badge")
    assert response.status_code == 200
    assert "1 unpublished change" in response.text

    response = client.get("/git_publish")
    assert response.status_code == 200
    assert "Requirements" in response.text
    assert "requirements.sdoc" in response.text
    assert "notes.txt" not in response.text

    # A path that is not a managed file is refused.
    response = client.delete("/git_publish/discard?path=notes.txt&confirmed=1")
    assert response.status_code == 404
    response = client.delete(
        "/git_publish/discard?path=../outside.sdoc&confirmed=1"
    )
    assert response.status_code == 404

    # Without confirmation, the server returns the dialog and changes nothing.
    response = client.delete("/git_publish/discard?path=requirements.sdoc")
    assert response.status_code == 200
    assert "This cannot be undone." in response.text
    with open(path_to_document, encoding="utf8") as file_:
        assert file_.read() != DOCUMENT_CONTENT

    response = client.delete(
        "/git_publish/discard?path=requirements.sdoc&confirmed=1",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/git_publish"
    with open(path_to_document, encoding="utf8") as file_:
        assert file_.read() == DOCUMENT_CONTENT
    with open(path_to_notes, encoding="utf8") as file_:
        assert file_.read() == "Notes\n\n"

    response = client.get("/git_publish/badge")
    assert "All changes published" in response.text


def test_discard_is_refused_on_network_address(tmp_path):
    path_to_repository = str(tmp_path)
    _create_repository(path_to_repository)
    path_to_document = os.path.join(path_to_repository, "requirements.sdoc")
    _modify_file(path_to_document)

    client = TestClient(
        create_app(
            project_config=_create_project_config(path_to_repository, "0.0.0.0")
        )
    )

    response = client.get("/git_publish")
    assert response.status_code == 200
    assert "requirements.sdoc" in response.text
    assert "Discarding changes is disabled" in response.text

    response = client.delete(
        "/git_publish/discard?path=requirements.sdoc&confirmed=1"
    )
    assert response.status_code == 403
    with open(path_to_document, encoding="utf8") as file_:
        assert file_.read() != DOCUMENT_CONTENT
