from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        typst_template="company-report",
        typst_kroki=True,
    )
