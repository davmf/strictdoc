import sys

from strictdoc.backend.sysml.sysml_format import SysMLFormat
from strictdoc.core.project_config import ProjectConfig, ProjectFeature
from strictdoc.features.project_actions.project_action import (
    ProjectAction,
    ProjectActionParameter,
)


def create_config() -> ProjectConfig:
    return ProjectConfig(
        formats=[*ProjectConfig.default_formats(), SysMLFormat()],
        project_features=[ProjectFeature.PROJECT_ACTIONS],
        project_actions=[
            ProjectAction(
                handle="bounds",
                title="Bounds",
                argv=[sys.executable, "-c", "print('bounds')"],
                parameters=[
                    ProjectActionParameter(
                        name="horizon_h",
                        flag="--horizon-h",
                        kind="float",
                        default=8.0,
                    ),
                ],
            ),
        ],
    )
