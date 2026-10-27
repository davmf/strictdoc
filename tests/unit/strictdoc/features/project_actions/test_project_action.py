import pytest

from strictdoc.features.project_actions.project_action import (
    ProjectAction,
    ProjectActionParameter,
    ProjectActionSysMLBinding,
    ProjectActionValidationError,
    build_argv,
    validate_project_actions,
)


def _simulate_action() -> ProjectAction:
    return ProjectAction(
        handle="simulate",
        title="Simulate",
        argv=["python", "tools/run.py", "simulate"],
        parameters=[
            ProjectActionParameter(
                name="scenario",
                flag="--scenario",
                kind="choice",
                choices=["baseBatch", "baseSteady"],
                required=True,
            ),
            ProjectActionParameter(
                name="replications", flag="--replications", kind="integer"
            ),
            ProjectActionParameter(
                name="horizon_h", flag="--horizon-h", kind="float"
            ),
            ProjectActionParameter(name="live", flag="--live", kind="boolean"),
            ProjectActionParameter(name="video", flag="--video", kind="string"),
        ],
        sysml_binding=ProjectActionSysMLBinding(
            element_kind="part", specializes="Scenario", parameter="scenario"
        ),
    )


def test_01_build_argv_appends_flags_and_values_in_declaration_order():
    argv = build_argv(
        _simulate_action(),
        {
            "video": "build/media/x.mp4",
            "scenario": "baseSteady",
            "horizon_h": "-0.5",
            "live": "true",
            "replications": " 10 ",
        },
    )
    assert argv == [
        "python",
        "tools/run.py",
        "simulate",
        "--scenario",
        "baseSteady",
        "--replications",
        "10",
        "--horizon-h",
        "-0.5",
        "--live",
        "--video",
        "build/media/x.mp4",
    ]


def test_02_build_argv_omits_empty_optional_values_and_false_booleans():
    argv = build_argv(
        _simulate_action(), {"scenario": "baseBatch", "live": "false"}
    )
    assert argv == [
        "python",
        "tools/run.py",
        "simulate",
        "--scenario",
        "baseBatch",
    ]


def test_03_build_argv_reports_every_invalid_field():
    with pytest.raises(ProjectActionValidationError) as error_:
        build_argv(
            _simulate_action(),
            {
                "replications": "ten",
                "horizon_h": "1h",
                "live": "maybe",
                "video": "--help",
            },
        )
    assert error_.value.errors == {
        "scenario": "A value is required.",
        "replications": "Must be an integer.",
        "horizon_h": "Must be a number.",
        "live": "Must be true or false.",
        "video": "Must not start with '-'.",
    }


def test_04_build_argv_rejects_a_value_outside_the_choices():
    with pytest.raises(ProjectActionValidationError) as error_:
        build_argv(_simulate_action(), {"scenario": "baseSteady; rm -rf /"})
    assert error_.value.errors == {
        "scenario": "Must be one of: baseBatch, baseSteady."
    }


@pytest.mark.parametrize(
    "action, message",
    [
        (
            ProjectAction(handle="Run-All", title="Run", argv=["x"]),
            "config: project_actions: Run-All: handle must be snake_case.",
        ),
        (
            ProjectAction(handle="run", title="Run", argv=[]),
            (
                "config: project_actions: run: argv must be a non-empty list "
                "of str."
            ),
        ),
        (
            ProjectAction(
                handle="run",
                title="Run",
                argv=["x"],
                parameters=[
                    ProjectActionParameter(name="n", flag="-n", kind="date")
                ],
            ),
            (
                "config: project_actions: run: parameter n: unknown kind: date. "
                "Expected one of: choice, integer, float, boolean, string."
            ),
        ),
        (
            ProjectAction(
                handle="run",
                title="Run",
                argv=["x"],
                parameters=[
                    ProjectActionParameter(name="s", flag="-s", kind="choice")
                ],
            ),
            (
                "config: project_actions: run: parameter s: a choice parameter "
                "needs choices."
            ),
        ),
        (
            ProjectAction(
                handle="run",
                title="Run",
                argv=["x"],
                parameters=[
                    ProjectActionParameter(
                        name="n", flag="-n", kind="integer", default="many"
                    )
                ],
            ),
            (
                "config: project_actions: run: parameter n: default: Must be an "
                "integer."
            ),
        ),
        (
            ProjectAction(
                handle="run",
                title="Run",
                argv=["x"],
                sysml_binding=ProjectActionSysMLBinding(
                    element_kind="part",
                    specializes="Scenario",
                    parameter="scenario",
                ),
            ),
            (
                "config: project_actions: run: sysml_binding: unknown "
                "parameter: scenario."
            ),
        ),
    ],
)
def test_05_validate_project_actions_rejects_invalid_declarations(
    action, message
):
    with pytest.raises(ValueError) as error_:
        validate_project_actions([action])
    assert str(error_.value) == message


def test_06_validate_project_actions_rejects_duplicate_handles():
    action = ProjectAction(handle="run", title="Run", argv=["x"])
    with pytest.raises(ValueError) as error_:
        validate_project_actions([action, action])
    assert (
        str(error_.value) == "config: project_actions: run: duplicate handle."
    )
