import os
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectFeature
from strictdoc.features.project_actions.project_action import (
    ProjectAction,
    ProjectActionParameter,
)
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = os.path.dirname(os.path.abspath(__file__))

ACTIONS = [
    ProjectAction(
        handle="write_plot",
        title="Write plot",
        argv=[sys.executable, "scripts/write_plot.py"],
        parameters=[
            ProjectActionParameter(
                name="name",
                flag="--name",
                kind="choice",
                choices=["first", "second"],
                required=True,
            ),
            ProjectActionParameter(
                name="count", flag="--count", kind="integer", default=2
            ),
        ],
        outputs=["out/*.svg"],
    ),
    ProjectAction(
        handle="wait",
        title="Wait",
        argv=[sys.executable, "scripts/wait.py"],
    ),
    ProjectAction(
        handle="fail",
        title="Fail",
        argv=[sys.executable, "-c", "import sys; sys.exit(3)"],
    ),
    ProjectAction(
        handle="missing",
        title="Missing program",
        argv=["strictdoc-test-program-that-does-not-exist"],
    ),
]


def _create_client(project_root, *, host="127.0.0.1", features=None):
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=str(project_root),
        output_path=os.path.join(str(project_root), "output"),
        config=None,
        reload=False,
        host=host,
        port=8001,
    )
    project_config = ProjectConfig(
        project_features=(
            features
            if features is not None
            else [ProjectFeature.PROJECT_ACTIONS]
        ),
        project_actions=ACTIONS,
    )
    project_config.integrate_server_config(server_config)
    return TestClient(create_app(project_config=project_config))


@pytest.fixture
def project_root(tmp_path):
    shutil.copytree(
        os.path.join(PATH_TO_THIS_TEST_FOLDER, "input"),
        tmp_path,
        dirs_exist_ok=True,
    )
    return tmp_path


def _run(client, form):
    return client.post(
        "/project_actions/run", data=form, follow_redirects=False
    )


def _wait_until_finished(client, run_id):
    """The stream ends after the run and the rebuild have finished."""
    response = client.get(f"/project_actions/stream?run_id={run_id}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return response.text


def test_01_screen_is_412_when_feature_is_not_activated(project_root):
    client = _create_client(project_root, features=[])
    assert client.get("/project_actions").status_code == 412
    assert _run(client, {"action": "fail"}).status_code == 412
    assert client.get("/project_actions/stream?run_id=1").status_code == 412


def test_02_screen_lists_actions_with_defaults(project_root):
    client = _create_client(project_root)
    response = client.get("/project_actions")
    assert response.status_code == 200
    assert 'data-testid="project-action-write_plot"' in response.text
    assert 'data-testid="project-action-wait"' in response.text
    assert 'name="count"' in response.text
    assert 'value="2"' in response.text
    assert 'data-testid="project-tree-link-project-actions"' in response.text


def test_03_run_streams_output_and_shows_changed_outputs(project_root):
    client = _create_client(project_root)
    response = _run(
        client, {"action": "write_plot", "name": "first", "count": "2"}
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/project_actions"

    stream = _wait_until_finished(client, run_id=1)
    assert stream.split("event: finished")[0].count("data: ") == 3
    assert 'data: "line 0"' in stream
    assert 'data: "line 1"' in stream
    assert 'data: "done"' in stream
    assert stream.endswith("event: finished\ndata: {}\n\n")

    screen = client.get("/project_actions").text
    assert 'data-run-state="succeeded"' in screen
    assert "exit code 0" in screen
    assert "out/first.svg" in screen
    assert 'src="/project_actions/output/1/out/first.svg"' in screen

    output = client.get("/project_actions/output/1/out/first.svg")
    assert output.status_code == 200
    assert output.text.startswith("<svg")

    # A second run shows only the files that it changed.
    _run(client, {"action": "write_plot", "name": "second", "count": "1"})
    _wait_until_finished(client, run_id=2)
    screen = client.get("/project_actions").text
    assert "out/second.svg" in screen
    assert "out/first.svg" not in screen


def test_04_output_endpoint_serves_only_outputs_of_the_last_run(project_root):
    client = _create_client(project_root)
    _run(client, {"action": "write_plot", "name": "first"})
    _wait_until_finished(client, run_id=1)

    assert client.get("/project_actions/output/1/sample.sdoc").status_code == (
        404
    )
    assert (
        client.get("/project_actions/output/1/../sample.sdoc").status_code
        == 404
    )
    assert (
        client.get("/project_actions/output/2/out/first.svg").status_code == 404
    )


def test_05_invalid_parameters_are_reported_without_starting_a_run(
    project_root,
):
    client = _create_client(project_root)
    response = _run(
        client, {"action": "write_plot", "name": "third", "count": "x"}
    )
    assert response.status_code == 422
    assert "Must be one of: first, second." in response.text
    assert "Must be an integer." in response.text
    assert 'data-testid="project-actions-run"' not in response.text

    response = _run(client, {"action": "unknown"})
    assert response.status_code == 404
    assert "Unknown action: unknown." in response.text


def test_06_second_run_is_rejected_while_busy_and_cancel_stops_it(
    project_root,
):
    client = _create_client(project_root)
    assert _run(client, {"action": "wait"}).status_code == 303

    response = _run(client, {"action": "fail"})
    assert response.status_code == 409
    assert "The action &#39;Wait&#39; is still running." in response.text

    screen = client.get("/project_actions").text
    assert 'data-run-state="running"' in screen
    assert 'data-testid="project-actions-cancel"' in screen

    response = client.post("/project_actions/cancel", follow_redirects=False)
    assert response.status_code == 303
    _wait_until_finished(client, run_id=1)
    screen = client.get("/project_actions").text
    assert 'data-run-state="cancelled"' in screen


def test_07_failed_and_unstartable_runs_are_reported(project_root):
    client = _create_client(project_root)
    _run(client, {"action": "fail"})
    _wait_until_finished(client, run_id=1)
    screen = client.get("/project_actions").text
    assert 'data-run-state="failed"' in screen
    assert "exit code 3" in screen

    _run(client, {"action": "missing"})
    _wait_until_finished(client, run_id=2)
    screen = client.get("/project_actions").text
    assert 'data-run-state="error"' in screen
    assert "strictdoc-test-program-that-does-not-exist" in screen


def test_08_runs_are_disabled_on_a_non_loopback_host(project_root):
    client = _create_client(project_root, host="0.0.0.0")
    screen = client.get("/project_actions").text
    assert 'data-testid="project-actions-remote-disabled"' in screen

    response = _run(client, {"action": "fail"})
    assert response.status_code == 403
    assert 'data-testid="project-actions-run"' not in response.text
