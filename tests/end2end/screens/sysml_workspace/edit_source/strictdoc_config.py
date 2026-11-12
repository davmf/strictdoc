from strictdoc.backend.sysml.sysml_format import SysMLFormat
from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        project_title="Kettle",
        formats=[
            *ProjectConfig.default_formats(),
            SysMLFormat(tracker_layout=True),
        ],
    )
