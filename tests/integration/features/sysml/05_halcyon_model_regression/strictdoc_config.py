"""StrictDoc project configuration: reads the SysML v2 model directly."""

from strictdoc.backend.sysml.sysml_format import SysMLFormat
from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        project_title="Halcyon dPCR-24",
        formats=[*ProjectConfig.default_formats(), SysMLFormat()],
    )
