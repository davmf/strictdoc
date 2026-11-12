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
            self.open(
                test_server.get_host_and_port() + "/workspace?item=BEH-001"
            )

            screen = Screen_SysMLWorkspace(self)
            screen.assert_entry_title("kettle")
            screen.do_save_as_view()

            # The new view draws the whole state machine.
            screen.assert_entry_title("kettle view")
            screen.assert_selected_in_tree("BEH-002")
            screen.assert_view_editor()
            screen.assert_diagram_drawn()

            # The preview follows the fields before they are saved.
            screen.do_fill_view_field("exposes", "")
            screen.do_add_expose("'BEH-001'::top::heating")
            screen.do_fill_view_field("options", "transitions=primary")
            screen.assert_preview("preview")

            # An unknown state is an error of the preview.
            screen.do_fill_view_field("exposes", "'BEH-001'::top::nothing")
            screen.assert_preview("error")
            screen.do_fill_view_field("exposes", "'BEH-001'::top::heating")
            screen.assert_preview("preview")

            screen.do_save_view()
            screen.assert_view_editor()
            screen.assert_diagram_drawn()
            screen.assert_no_js_errors()

        with open(
            os.path.join(
                test_setup.path_to_sandbox, "TRK-BEH", "BEH-002.sysml"
            ),
            encoding="utf-8",
        ) as file_:
            text = file_.read()
        assert "        expose 'BEH-001'::top::heating;\n" in text
        assert '            options = "transitions=primary";\n' in text
