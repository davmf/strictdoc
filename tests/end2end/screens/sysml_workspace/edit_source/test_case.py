import os

from selenium.webdriver.common.keys import Keys

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
            screen.do_open_source_editor()
            screen.assert_diagram_drawn()

            # A new state: the diagram previews it before the save.
            screen.do_type_after_line("part idle", "part dry : State;")
            screen.assert_source_preview()

            # A syntax error is a problem of the editor, not a save.
            screen.do_type_in_source(" }")
            screen.assert_source_problems(1)
            screen.do_type_in_source(Keys.BACKSPACE * 2)
            screen.assert_source_problems(0)
            screen.assert_source_preview()

            screen.do_save_source_with_shortcut()
            screen.assert_entry_title("kettle")
            screen.assert_diagram_drawn()
            screen.assert_no_js_errors()

        with open(
            os.path.join(
                test_setup.path_to_sandbox, "TRK-BEH", "BEH-001.sysml"
            ),
            encoding="utf-8",
        ) as file_:
            text = file_.read()
        # The editor indents a new line with the four spaces of the file.
        assert "            part dry : State;\n" in text
