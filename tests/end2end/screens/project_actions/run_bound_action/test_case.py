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

STEADY_NODE_XPATH = (
    "(//sdoc-node[.//*[normalize-space(text())='Scenarios::steady']])[1]"
)
INSTRUMENT_NODE_XPATH = (
    "(//sdoc-node[.//*[normalize-space(text())='Scenarios::instrument']])[1]"
)


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
            screen_document = screen_project_index.do_click_on_first_document()
            screen_document.assert_on_screen_document()

            # Only the part usage typed by a Scenario offers the action.
            self.assert_element_not_present(
                f"{INSTRUMENT_NODE_XPATH}"
                "//*[@data-testid='node-project-action-simulate']",
                by=By.XPATH,
            )
            self.hover_and_click(
                hover_selector=STEADY_NODE_XPATH,
                click_selector=(
                    f"{STEADY_NODE_XPATH}"
                    "//*[@data-testid='node-project-action-simulate']"
                ),
                hover_by=By.XPATH,
                click_by=By.XPATH,
            )

            screen_actions = Screen_ProjectActions(self)
            screen_actions.assert_on_screen()
            screen_actions.assert_parameter_value(
                "simulate", "scenario", "steady"
            )
            screen_actions.do_fill_in_parameter("simulate", "replications", "3")
            screen_actions.do_run("simulate")

            screen_actions.assert_run_state("succeeded")
            screen_actions.assert_log_contains("steady: replication 3")
            screen_actions.assert_output_image("out/steady.svg")
