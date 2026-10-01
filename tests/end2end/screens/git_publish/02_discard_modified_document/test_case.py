"""
@relation(SDOC-SRS-210, scope=file)
"""

import os
import tempfile

from tests.end2end.e2e_case import E2ECase
from tests.end2end.helpers.screens.git_publish.git_publish_repository import (
    GitPublishRepository,
)
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
            repository = GitPublishRepository(path_to_temp_folder_)
            repository.init()
            for file_name_ in ("strictdoc_config.py", "requirements.sdoc"):
                repository.copy_file(
                    os.path.join(path_to_this_test_file_folder, file_name_),
                    file_name_,
                )
            repository.commit_all("Initial commit")

            with SDocTestServer(
                input_path=repository.path_to_root,
                cwd=repository.path_to_root,
            ) as test_server:
                self.open(test_server.get_host_and_port())

                screen_project_index = Screen_ProjectIndex(self)
                screen_project_index.assert_on_screen()

                screen_document = (
                    screen_project_index.do_click_on_first_document()
                )
                screen_document.assert_on_screen_document()
                form_edit_requirement = screen_document.get_node(
                    1
                ).do_open_form_edit_requirement()
                form_edit_requirement.do_fill_in_field_statement(
                    "The system shall do B."
                )
                form_edit_requirement.do_form_submit()

                screen_git_publish = Screen_GitPublish(self)
                screen_git_publish.assert_badge_text("1 unpublished change")
                assert (
                    repository.get_porcelain_status(["requirements.sdoc"])
                    == " M requirements.sdoc\n"
                )

                screen_git_publish.do_click_on_badge()
                screen_git_publish.do_discard_change(
                    "requirements.sdoc",
                    "StrictDoc will restore the file to its last published "
                    "state. This cannot be undone.",
                )
                screen_git_publish.assert_summary("All changes published")
                screen_git_publish.assert_badge_text("All changes published")

                # The file matches HEAD again.
                assert (
                    repository.get_porcelain_status(["requirements.sdoc"]) == ""
                )

                # The document shows the old content.
                self.open(test_server.get_host_and_port())
                screen_project_index.assert_on_screen()
                screen_document = (
                    screen_project_index.do_click_on_first_document()
                )
                screen_document.assert_on_screen_document()
                screen_document.get_node(
                    1
                ).assert_requirement_statement_contains(
                    "The system shall do A."
                )
