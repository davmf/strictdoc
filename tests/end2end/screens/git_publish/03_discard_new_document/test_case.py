"""
@relation(SDOC-SRS-210, scope=file)
"""

import os
import tempfile

from selenium.webdriver.common.by import By

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

                form_add_document = (
                    screen_project_index.do_open_modal_form_add_document()
                )
                form_add_document.do_fill_in_title("Document 2")
                form_add_document.do_fill_in_path("docs/document2.sdoc")
                form_add_document.do_form_submit()
                screen_project_index.assert_contains_document("Document 2")
                assert repository.exists("docs/document2.sdoc")

                screen_git_publish = Screen_GitPublish(self)
                screen_git_publish.assert_badge_text("1 unpublished change")
                screen_git_publish.do_click_on_badge()
                screen_git_publish.assert_change(
                    "docs/document2.sdoc", "Document 2", "new"
                )
                screen_git_publish.do_discard_change(
                    "docs/document2.sdoc",
                    "This is a new file. StrictDoc will delete it.",
                )
                screen_git_publish.assert_summary("All changes published")

                assert not repository.exists("docs/document2.sdoc")

                self.open(test_server.get_host_and_port())
                screen_project_index.assert_on_screen()
                screen_project_index.assert_contains_document("Requirements")
                self.assert_element_not_present(
                    "//*[@data-testid='tree-file-link']"
                    "//*[contains(., 'Document 2')]",
                    by=By.XPATH,
                )
