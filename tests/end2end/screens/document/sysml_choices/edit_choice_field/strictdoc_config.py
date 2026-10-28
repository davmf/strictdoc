from strictdoc.backend.sysml.sysml_format import SysMLFormat
from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        formats=[
            *ProjectConfig.default_formats(),
            SysMLFormat(),
        ],
    )
