import os

from tests.end2end.e2e_case import E2ECase
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer

path_to_this_test_file_folder = os.path.dirname(os.path.abspath(__file__))

# Loading the PlantUML engine and rendering take a few seconds.
RENDER_TIMEOUT = 30


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

            # The state machine is drawn by the StateMachineProfile, which
            # the engine finds without a view.
            screen_document = (
                screen_project_index.do_click_on_the_document_with_title(
                    "DoorController"
                )
            )
            screen_document.assert_on_screen_document()
            self.assert_element(
                'div.sysml_diagram[data-processed="true"] svg',
                timeout=RENDER_TIMEOUT,
            )
            self.assert_element_not_present("pre.mermaid")
            self.assert_element_not_present("pre.sysml_diagram__error")

            # A requirements package shows its requirements, and each
            # requirement a trace diagram, laid out with ELK, that is drawn
            # when it scrolls into view. The trace reaches the design
            # element of another file that satisfies the requirement.
            self.open(test_server.get_host_and_port())
            screen_document = (
                screen_project_index.do_click_on_the_document_with_title(
                    "DoorRequirements"
                )
            )
            screen_document.assert_on_screen_document()
            self.assert_element(
                'div.sysml_diagram[data-sysml-options^="view=requirements'
                ' root="] svg',
                timeout=RENDER_TIMEOUT,
            )
            trace_diagram = (
                'div.sysml_diagram[data-sysml-options="view=requirements'
                ' focus=DOOR-REQ-1 depth=1"]'
            )
            self.scroll_to(trace_diagram)
            self.assert_element(f"{trace_diagram} svg", timeout=RENDER_TIMEOUT)
            self.assert_text("motor", f"{trace_diagram} svg")
            self.assert_element_not_present("pre.sysml_diagram__error")

            # A design package shows a class diagram of its definitions.
            self.open(test_server.get_host_and_port())
            screen_document = (
                screen_project_index.do_click_on_the_document_with_title(
                    "DoorDesign"
                )
            )
            screen_document.assert_on_screen_document()
            self.assert_element(
                'div.sysml_diagram[data-sysml-options^="view=definitions"] svg',
                timeout=RENDER_TIMEOUT,
            )
            self.assert_text("Motor", "div.sysml_diagram svg")
            self.assert_element_not_present("pre.sysml_diagram__error")
