import sys

from strictdoc.backend.sysml.sysml_format import SysMLFormat
from strictdoc.core.project_config import ProjectConfig, ProjectFeature
from strictdoc.features.project_actions.project_action import (
    ProjectAction,
    ProjectActionParameter,
    ProjectActionSysMLBinding,
)


def create_config() -> ProjectConfig:
    return ProjectConfig(
        formats=[*ProjectConfig.default_formats(), SysMLFormat()],
        project_features=[ProjectFeature.PROJECT_ACTIONS],
        project_actions=[
            ProjectAction(
                handle="simulate",
                title="Simulate",
                argv=[sys.executable, "scripts/simulate.py"],
                parameters=[
                    ProjectActionParameter(
                        name="scenario",
                        flag="--scenario",
                        kind="choice",
                        choices=["steady"],
                        required=True,
                    ),
                    ProjectActionParameter(
                        name="replications",
                        flag="--replications",
                        kind="integer",
                        default=1,
                    ),
                ],
                outputs=["out/*.svg"],
                sysml_binding=ProjectActionSysMLBinding(
                    element_kind="part",
                    specializes="Scenario",
                    parameter="scenario",
                ),
            ),
        ],
    )
