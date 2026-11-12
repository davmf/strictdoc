from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from tests.end2end.helpers.screens.screen import Screen

# Drawing loads the PlantUML engine, which takes a while the first time.
DIAGRAM_TIMEOUT_SECONDS = 60


class Screen_SysMLWorkspace(Screen):  # pylint: disable=invalid-name
    def assert_on_screen(self) -> None:
        self.test_case.assert_element(
            "//*[@data-testid='sysml-workspace-tree']", by=By.XPATH
        )

    def assert_entry_title(self, title: str) -> None:
        self.test_case.assert_element(
            "//*[@data-testid='sysml-workspace-entry-title']"
            f"[normalize-space(text())='{title}']",
            by=By.XPATH,
        )

    def assert_selected_in_tree(self, entry_id: str) -> None:
        self.test_case.assert_element(
            "//*[@data-testid='sysml-workspace-tree']"
            f"//a[contains(@class, 'sysml-ws-selected')]"
            f"[@data-entry-id='{entry_id}']",
            by=By.XPATH,
        )

    def assert_tree_entry_visible(self, entry_id: str) -> None:
        self.test_case.assert_element_visible(
            self._tree_link(entry_id), by=By.XPATH
        )

    def assert_tree_entry_hidden(self, entry_id: str) -> None:
        self.test_case.assert_element_not_visible(
            self._tree_link(entry_id), by=By.XPATH
        )

    def assert_relation(self, entry_id: str) -> None:
        self.test_case.assert_element(
            "//*[@data-testid='sysml-workspace-relations']"
            f"//a[@data-entry-id='{entry_id}']",
            by=By.XPATH,
        )

    def assert_diagram_drawn(self) -> None:
        self.test_case.assert_element(
            "//*[@data-testid='sysml-workspace-diagram']"
            "[@data-sysml-state='drawn']//*[name()='svg']",
            by=By.XPATH,
            timeout=DIAGRAM_TIMEOUT_SECONDS,
        )

    def do_toggle(self, entry_id: str) -> None:
        self.test_case.click_xpath(
            f"//li[@data-entry-id='{entry_id}']"
            "/div/button[contains(@class, 'sysml-ws-toggle')]"
        )

    def do_click_tree_entry(self, entry_id: str) -> None:
        self.test_case.click_xpath(self._tree_link(entry_id))

    def do_click_relation(self, entry_id: str) -> None:
        self.test_case.click_xpath(
            "//*[@data-testid='sysml-workspace-relations']"
            f"//a[@data-entry-id='{entry_id}']"
        )

    def do_filter(self, text: str) -> None:
        self.test_case.type(
            "//*[@data-testid='sysml-workspace-filter']", text, by=By.XPATH
        )

    def do_clear_filter(self) -> None:
        # Clearing a field from Selenium fires no input event: send the
        # backspaces a user would type.
        selector = "//*[@data-testid='sysml-workspace-filter']"
        value = self.test_case.get_attribute(selector, "value", by=By.XPATH)
        self.test_case.add_text(selector, "\b" * len(value), by=By.XPATH)

    def do_create_item(self, kind: str, title: str) -> None:
        form = "//*[@data-testid='sysml-workspace-new-item']"
        Select(
            self.test_case.find_element(f"{form}//select", by=By.XPATH)
        ).select_by_value(kind)
        self.test_case.type(f"{form}//input[@name='title']", title, by=By.XPATH)
        self.test_case.click_xpath(f"{form}//button[@type='submit']")

    @staticmethod
    def _tree_link(entry_id: str) -> str:
        return (
            "//*[@data-testid='sysml-workspace-tree']"
            f"//a[@data-entry-id='{entry_id}']"
        )
