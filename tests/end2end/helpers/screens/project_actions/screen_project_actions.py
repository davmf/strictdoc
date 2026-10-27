from selenium.webdriver.common.by import By

from tests.end2end.helpers.screens.screen import Screen


class Screen_ProjectActions(Screen):  # pylint: disable=invalid-name
    def assert_on_screen(self):
        self.test_case.assert_element(
            "//*[@data-testid='project-actions-screen']", by=By.XPATH
        )

    def assert_parameter_value(
        self, action_handle: str, parameter_name: str, value: str
    ) -> None:
        self.test_case.assert_attribute(
            "//*[@data-testid="
            f"'project-action-{action_handle}-{parameter_name}']",
            "value",
            value,
            by=By.XPATH,
        )

    def do_fill_in_parameter(
        self, action_handle: str, parameter_name: str, value: str
    ) -> None:
        self.test_case.type(
            "//*[@data-testid="
            f"'project-action-{action_handle}-{parameter_name}']",
            value,
            by=By.XPATH,
        )

    def do_run(self, action_handle: str) -> None:
        self.test_case.click_xpath(
            f"//*[@data-testid='project-action-{action_handle}-submit']"
        )

    def assert_run_state(self, state: str) -> None:
        # A running action reloads the page when it finishes, so the final
        # state can take a few seconds to appear.
        self.test_case.assert_element(
            "//*[@data-testid='project-actions-run-state']"
            f"[normalize-space(text())='{state}']",
            by=By.XPATH,
            timeout=30,
        )

    def assert_log_contains(self, text: str) -> None:
        self.test_case.assert_text(
            text, "//*[@data-testid='project-actions-log']", by=By.XPATH
        )

    def assert_output_image(self, relative_path: str) -> None:
        self.test_case.assert_element(
            "//*[@data-testid='project-actions-output']"
            f"//img[@alt='{relative_path}']",
            by=By.XPATH,
        )

    def assert_parameter_error(
        self, action_handle: str, parameter_name: str, text: str
    ) -> None:
        self.test_case.assert_text(
            text,
            "//*[@data-testid="
            f"'project-action-{action_handle}-{parameter_name}-error']",
            by=By.XPATH,
        )
