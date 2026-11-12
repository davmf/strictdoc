from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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

    def do_save_as_view(self) -> None:
        self.test_case.click_xpath(
            "//*[@data-testid='sysml-workspace-save-as-view']/summary"
        )
        self.test_case.click_xpath(
            "//*[@data-testid='sysml-workspace-save-as-view-form']"
            "//button[@type='submit']"
        )

    def assert_view_editor(self) -> None:
        self.test_case.assert_element(
            "//*[@data-testid='sysml-workspace-view-editor']", by=By.XPATH
        )

    def do_fill_view_field(self, field: str, text: str) -> None:
        self.test_case.type(
            f"//*[@data-testid='sysml-workspace-view-{field}']",
            text,
            by=By.XPATH,
        )

    def do_add_expose(self, text: str) -> None:
        self.test_case.type(
            "//*[@data-testid='sysml-workspace-view-add-expose']",
            text,
            by=By.XPATH,
        )
        self.test_case.click_xpath("//button[@data-action='add-expose']")

    def assert_preview(self, state: str) -> None:
        self.test_case.assert_element(
            "//*[@data-testid='sysml-workspace-preview-state']"
            f"[@data-state='{state}']",
            by=By.XPATH,
            timeout=DIAGRAM_TIMEOUT_SECONDS,
        )

    def do_save_view(self) -> None:
        self.test_case.click_xpath(
            "//*[@data-testid='sysml-workspace-view-save']"
        )

    def do_open_source_editor(self) -> None:
        self.test_case.click_xpath(
            "//details[contains(@class, 'sysml-ws-source')]/summary"
        )
        self.test_case.click_xpath(
            "//*[@data-testid='sysml-workspace-edit-source']"
        )
        self.test_case.assert_element(
            "//form[@data-editor-ready='true']", by=By.XPATH
        )

    def do_type_after_line(self, line_text: str, text: str) -> None:
        """Type a new line in the source editor after the line with line_text."""
        line = self.test_case.find_element(
            f"//div[contains(@class, 'cm-line')][contains(., \"{line_text}\")]",
            by=By.XPATH,
        )
        line.click()
        line.send_keys(Keys.END, Keys.ENTER, text)

    def do_type_in_source(self, keys: str) -> None:
        self.test_case.find_element(
            "//div[contains(@class, 'cm-content')]", by=By.XPATH
        ).send_keys(keys)

    def assert_source_problems(self, count: int) -> None:
        self.test_case.assert_element(
            f"//form[@data-problems='{count}']", by=By.XPATH, timeout=30
        )

    def assert_source_preview(self) -> None:
        self.test_case.assert_element(
            "//*[@data-testid='sysml-workspace-source-state']"
            "[@data-state='preview']",
            by=By.XPATH,
            timeout=DIAGRAM_TIMEOUT_SECONDS,
        )

    def do_save_source_with_shortcut(self) -> None:
        self.test_case.find_element(
            "//div[contains(@class, 'cm-content')]", by=By.XPATH
        ).send_keys(Keys.CONTROL, "s")

    @staticmethod
    def _tree_link(entry_id: str) -> str:
        return (
            "//*[@data-testid='sysml-workspace-tree']"
            f"//a[@data-entry-id='{entry_id}']"
        )
