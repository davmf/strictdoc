"""The files that the Typst export writes next to the exported documents."""

import os
from typing import FrozenSet

from strictdoc.core.project_config import ProjectConfig

PATH_TO_ASSETS = os.path.join(os.path.dirname(__file__), "assets")
PATH_TO_STRICTDOC_TYP = os.path.join(PATH_TO_ASSETS, "strictdoc.typ")
PATH_TO_STRICTDOC_REPORT_TYP = os.path.join(
    PATH_TO_ASSETS, "strictdoc-report.typ"
)


def get_template_file_name_bases(
    project_config: ProjectConfig,
) -> FrozenSet[str]:
    """
    The files of the export folder that are not documents: StrictDoc's own,
    and the external template and kroki.typ of the build. A document gets
    another name rather than overwrite one of them.
    """
    return frozenset(
        (
            "strictdoc",
            "strictdoc-report",
            "kroki",
            project_config.typst_template,
        )
    )
