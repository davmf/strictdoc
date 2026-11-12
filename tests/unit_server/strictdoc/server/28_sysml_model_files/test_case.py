"""
The SysML diagrams of the server: the route that gives the browser the SysML
files of the project, the diagram placeholder of a SysML document and the
scripts that draw it.
"""

import os
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


@pytest.fixture(name="client")
def fixture_client(tmp_path) -> TestClient:
    tmp_path = tmp_path / INPUT_FOLDER
    shutil.copytree(os.path.join(PATH_TO_THIS_TEST_FOLDER, "input"), tmp_path)
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=str(tmp_path),
        output_path=os.path.join(str(tmp_path), "output"),
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


def test_01_model_files_are_every_sysml_file_of_the_project(client):
    response = client.get("/sysml/model_files")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    files = {file_["name"]: file_["text"] for file_ in response.json()["files"]}
    assert sorted(files) == [
        "MODEL.sysml",
        "TRK-SC/SC-001.sysml",
        "TRK-SC/TRK-SC.sysml",
        "TRK-STK/STK-001.sysml",
        "TRK-STK/TRK-STK.sysml",
        "TRK-SYS/SYS-001.sysml",
        "TRK-SYS/SYS-002.sysml",
        "TRK-SYS/SYS-010.sysml",
        "TRK-SYS/SYS-F-HEATING.sysml",
        "TRK-SYS/SYS-F-SAFETY.sysml",
        "TRK-SYS/TRK-SYS.sysml",
        "_library/KettleLibrary.sysml",
    ]
    assert files["_library/KettleLibrary.sysml"].startswith(
        "library package KettleLibrary"
    )


def test_02_document_has_the_diagram_placeholder(client):
    response = client.get(f"/{INPUT_FOLDER}/TRK-SYS/TRK-SYS.html")
    assert response.status_code == 200
    assert (
        'data-sysml-options="view=requirements root=TRK-SYS depth=1 '
        'text=false links=/?a={id}"' in response.text
    )
    assert (
        '<script type="module" '
        'src="/_static/plantuml/sysml/sysml-diagrams.js"></script>'
    ) in response.text


def test_03_design_document_draws_its_definitions(client):
    response = client.get(f"/{INPUT_FOLDER}/TRK-SC/TRK-SC.html")
    assert response.status_code == 200
    assert 'data-sysml-options="view=definitions root=TRK-SC"' in (
        response.text
    )


@pytest.mark.parametrize(
    "path",
    [
        "/_static/plantuml/sysml/sysml-diagrams.js",
        "/_static/plantuml/sysml/plantuml-mit.js",
        "/_static/plantuml/sysml/elk.bundled.js",
        "/_static/plantuml/viz-global.js",
    ],
)
def test_04_the_scripts_are_served(client, path):
    assert client.get(path).status_code == 200
