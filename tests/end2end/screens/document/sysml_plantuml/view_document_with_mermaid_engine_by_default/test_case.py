import os

from tests.end2end.e2e_case import E2ECase
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer

path_to_this_test_file_folder = os.path.dirname(os.path.abspath(__file__))


class Test(E2ECase):
    def test(self):
        with SDocTestServer(
            input_path=os.path.join(path_to_this_test_file_folder, "input"),
            config_path=os.path.join(
                path_to_this_test_file_folder, "strictdoc_config.py"
            ),
        ) as test_server:
            self.open(test_server.get_host_and_port())

            screen_project_index = Screen_ProjectIndex(self)
            screen_project_index.assert_on_screen()
            screen_document = screen_project_index.do_click_on_first_document()
            screen_document.assert_on_screen_document()

            # Without diagram_engine, SysML documents keep the Mermaid
            # diagram.
            self.assert_element("pre.mermaid svg")
            self.assert_element_not_present("div.sysml_diagram")
            self.assert_element_not_present("div.sysml_sources")
