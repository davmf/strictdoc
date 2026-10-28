import os

from selenium.webdriver.common.by import By

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.document.form_edit_requirement import (
    Form_EditRequirement,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        # The SysML format is registered in the test folder's config, outside
        # the sandbox, so that the sandbox holds only the SysML files.
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
            screen_document = (
                screen_project_index.do_click_on_the_document_with_title(
                    "Requirements"
                )
            )
            screen_document.assert_on_screen_document()
            screen_document.assert_header_document_title("Requirements")

            # The first node is the diagram of the file. The enum literal is
            # shown as its bare name.
            requirement = screen_document.get_node(node_order=2)
            requirement.assert_field_contains("STATUS", "Draft")

            form_edit_requirement: Form_EditRequirement = (
                requirement.do_open_form_edit_requirement()
            )

            # A click on the empty field lists all literals of the enum.
            field_xpath = "//*[@data-testid='form-field-STATUS']"
            self.type(field_xpath, "", by=By.XPATH)
            self.click_xpath(field_xpath)
            for literal_ in ("Draft", "Waiting for approval", "Approved"):
                self.assert_element(
                    f"{field_xpath}/following-sibling::ul[1]"
                    f"//li[@data-autocompletable-value='{literal_}']",
                    by=By.XPATH,
                )

            form_edit_requirement.do_use_first_autocomplete_result(
                "form-field-STATUS", "Wait"
            )
            form_edit_requirement.do_form_submit()

            requirement.assert_field_contains("STATUS", "Waiting for approval")

        # StrictDoc writes the literal qualified by its type, and quoted.
        assert test_setup.compare_sandbox_and_expected_output()
