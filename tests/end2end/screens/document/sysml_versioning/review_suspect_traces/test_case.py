import os

from selenium.webdriver.common.by import By

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.document.screen_document import (
    Screen_Document,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer

REVIEW_ACTION_XPATH = "//*[@data-testid='node-review-sysml-traces-action']"


def node_xpath(uid: str) -> str:
    return f"(//sdoc-node[.//*[normalize-space(text())='{uid}']])[last()]"


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        # The SysML format is registered in the test folder's config, outside
        # the sandbox, so that the sandbox holds only the documents.
        path_to_config = os.path.join(
            test_setup.path_to_test_dir, "strictdoc_config.py"
        )
        with SDocTestServer(
            input_path=test_setup.path_to_sandbox,
            config_path=path_to_config,
        ) as test_server:
            self.open(test_server.get_host_and_port())

            screen_project_index = Screen_ProjectIndex(self)
            screen_project_index.assert_on_screen()

            # A trace in a requirements package.
            self.click_xpath(
                "//*[@data-testid='tree-file-link']"
                "[contains(., 'System requirements')]"
            )
            screen_document = Screen_Document(self)
            screen_document.assert_on_screen_document()
            screen_document.assert_text(
                "Suspect trace to STK-1: traced version 2, current version 3."
            )
            self.hover_and_click(
                hover_selector=node_xpath("SYS-1"),
                click_selector=node_xpath("SYS-1") + REVIEW_ACTION_XPATH,
                hover_by=By.XPATH,
                click_by=By.XPATH,
            )
            screen_document.assert_no_text("Suspect trace to STK-1")
            self.assert_element_not_present(REVIEW_ACTION_XPATH, by=By.XPATH)

            # A trace in a design package.
            self.open(test_server.get_host_and_port())
            screen_project_index.assert_on_screen()
            self.click_xpath(
                "//*[@data-testid='tree-file-link'][contains(., 'Design')]"
            )
            screen_document.assert_on_screen_document()
            screen_document.assert_text(
                "Suspect trace to SYS-1: traced version 1, current version 2."
            )
            self.hover_and_click(
                hover_selector=node_xpath("Design::Pump::pump"),
                click_selector=(
                    node_xpath("Design::Pump::pump") + REVIEW_ACTION_XPATH
                ),
                hover_by=By.XPATH,
                click_by=By.XPATH,
            )
            screen_document.assert_no_text("Suspect trace to SYS-1")
            self.assert_element_not_present(REVIEW_ACTION_XPATH, by=By.XPATH)

        assert test_setup.compare_sandbox_and_expected_output()
