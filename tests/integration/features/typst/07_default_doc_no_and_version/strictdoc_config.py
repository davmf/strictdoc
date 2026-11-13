from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        typst_default_doc_no="DOC-0000",
        typst_default_version="draft",
    )
