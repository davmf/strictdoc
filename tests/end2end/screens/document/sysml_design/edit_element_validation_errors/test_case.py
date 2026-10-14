import os

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.document.form_edit_sysml import (
    Form_EditSysMLElement,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer

VALVE_NODE_XPATH = (
    "(//sdoc-node[.//*[normalize-space(text())='Design::Valve']])[1]"
)


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
            screen_document = screen_project_index.do_click_on_first_document()
            screen_document.assert_on_screen_document()
            screen_document.assert_header_document_title("Design")

            form = Form_EditSysMLElement.open_for_node(self, VALVE_NODE_XPATH)

            # A table row with an unknown kind is rejected.
            new_row = form.do_add_member()
            form.do_fill_in_member(new_row, "kind", "widget")
            form.do_fill_in_member(new_row, "name", "w")
            form.do_form_submit_and_catch_error("Unknown kind 'widget'")

            # A satisfy statement with an unknown requirement UID is
            # rejected by the traceability check. The file is restored.
            form.do_delete_member(new_row)
            form.do_fill_in_source(
                "part def Valve {\n    satisfy 'SYS-NOPE-001' by valve;\n}"
            )
            form.do_form_submit_and_catch_error("SYS-NOPE-001")

            form.do_form_cancel()
            screen_document.assert_text("Design::Valve")

        assert test_setup.compare_sandbox_and_expected_output()
