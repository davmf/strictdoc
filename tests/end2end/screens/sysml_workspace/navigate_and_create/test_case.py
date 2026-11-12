import os

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.sysml_workspace.screen_sysml_workspace import (
    Screen_SysMLWorkspace,
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
            self.open(test_server.get_host_and_port() + "/workspace")

            screen = Screen_SysMLWorkspace(self)
            screen.assert_on_screen()
            screen.assert_entry_title("Kettle")

            # Selecting entries swaps the panes without loading the page.
            self.execute_script("window.sysmlWorkspaceTestMarker = true;")
            screen.do_click_tree_entry("TRK-SYS")
            screen.assert_entry_title("System requirements")
            screen.assert_selected_in_tree("TRK-SYS")

            screen.do_toggle("TRK-SYS")
            screen.do_toggle("SYS-F-HEATING")
            screen.do_click_tree_entry("SYS-001")
            screen.assert_entry_title("Boil time")
            screen.assert_relation("STK-001")
            screen.assert_relation("SC-001")
            screen.assert_diagram_drawn()

            screen.do_click_relation("STK-001")
            screen.assert_entry_title("Hot water")
            screen.assert_selected_in_tree("STK-001")
            assert self.execute_script(
                "return window.sysmlWorkspaceTestMarker === true;"
            )
            assert "item=STK-001" in self.get_current_url()

            # The browser history follows the selection.
            self.go_back()
            screen.assert_entry_title("Boil time")

            # The filter keeps the matching entries and their parents.
            screen.do_filter("dry")
            screen.assert_tree_entry_visible("SYS-010")
            screen.assert_tree_entry_visible("TRK-SYS")
            screen.assert_tree_entry_hidden("SYS-001")
            screen.assert_tree_entry_hidden("TRK-BEH")
            screen.do_clear_filter()
            screen.assert_tree_entry_visible("TRK-BEH")

            # A new state machine from its template, drawn at once.
            screen.do_click_tree_entry("TRK-BEH")
            screen.assert_entry_title("Behaviour")
            screen.do_create_item("statemachine", "Lid control")
            screen.assert_entry_title("Lid control")
            screen.assert_selected_in_tree("BEH-002")
            screen.assert_diagram_drawn()
            screen.assert_no_js_errors()

        assert os.path.isfile(
            os.path.join(test_setup.path_to_sandbox, "TRK-BEH", "BEH-002.sysml")
        )
