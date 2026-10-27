import os

from selenium.webdriver.common.by import By

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_actions.screen_project_actions import (
    Screen_ProjectActions,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

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
            self.click_xpath(
                "//*[@data-testid='project-tree-link-project-actions']"
            )

            screen_actions = Screen_ProjectActions(self)
            screen_actions.assert_on_screen()
            screen_actions.assert_parameter_value("bounds", "horizon_h", "8.0")
            screen_actions.do_fill_in_parameter("bounds", "horizon_h", "eight")
            screen_actions.do_run("bounds")

            screen_actions.assert_parameter_error(
                "bounds", "horizon_h", "Must be a number."
            )
            self.assert_element_not_present(
                "//*[@data-testid='project-actions-run']", by=By.XPATH
            )
