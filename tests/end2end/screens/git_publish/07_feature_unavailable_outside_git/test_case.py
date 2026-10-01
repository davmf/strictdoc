"""
@relation(SDOC-SRS-213, scope=file)
"""

import os
import shutil
import tempfile

from tests.end2end.e2e_case import E2ECase
from tests.end2end.helpers.screens.git_publish.screen_git_publish import (
    Screen_GitPublish,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer

path_to_this_test_file_folder = os.path.dirname(os.path.realpath(__file__))


class Test(E2ECase):
    def test(self):
        with tempfile.TemporaryDirectory() as path_to_temp_folder_:
            # realpath because macOS symlinks /var to /private/var.
            path_to_project = os.path.realpath(path_to_temp_folder_)
            # No "git init": the project is not in a Git repository.
            for file_name_ in ("strictdoc_config.py", "requirements.sdoc"):
                shutil.copyfile(
                    os.path.join(path_to_this_test_file_folder, file_name_),
                    os.path.join(path_to_project, file_name_),
                )

            with SDocTestServer(
                input_path=path_to_project,
                cwd=path_to_project,
            ) as test_server:
                self.open(test_server.get_host_and_port())

                screen_project_index = Screen_ProjectIndex(self)
                screen_project_index.assert_on_screen()
                screen_project_index.assert_contains_document("Requirements")

                screen_git_publish = Screen_GitPublish(self)
                screen_git_publish.assert_badge_text(
                    "Publishing is unavailable: "
                    "this project is not in a Git repository"
                )
                screen_git_publish.do_click_on_badge()
                screen_git_publish.assert_unavailable()
