# pylint: disable=invalid-name
from selenium.webdriver.common.by import By

from tests.end2end.e2e_case import E2ECase
from tests.end2end.helpers.form.form import Form


class Form_EditSysMLElement(Form):  # pylint: disable=invalid-name
    """The editor of a SysML design element: Tables and Source tabs."""

    MEMBER_ROW_XPATH = "(//*[@data-testid='sysml-member-row'])"

    @staticmethod
    def open_for_node(test_case: E2ECase, node_xpath: str):
        test_case.hover_and_click(
            hover_selector=node_xpath,
            click_selector=(
                f"{node_xpath}"
                "//*[@data-testid='node-edit-sysml-element-action']"
            ),
            hover_by=By.XPATH,
            click_by=By.XPATH,
        )
        test_case.assert_element(
            "//*[@data-testid='sysml-details-table']", by=By.XPATH
        )
        return Form_EditSysMLElement(test_case)

    def do_fill_in_details(self, column_key: str, value: str) -> None:
        self.test_case.type(
            f"//*[@data-testid='sysml-details-{column_key}']",
            value,
            by=By.XPATH,
        )

    def do_fill_in_member(
        self, row_order: int, column_key: str, value: str
    ) -> None:
        self.test_case.type(
            f"{self.MEMBER_ROW_XPATH}[{row_order}]"
            f"//*[@data-testid='sysml-member-{column_key}']",
            value,
            by=By.XPATH,
        )

    def do_add_member(self) -> int:
        """Add a MEMBERS row and return its order number."""
        rows_number = len(
            self.test_case.find_elements(self.MEMBER_ROW_XPATH, by=By.XPATH)
        )
        self.test_case.click_xpath(
            "//*[@data-testid='sysml-add-member-action']"
        )
        new_row_order = rows_number + 1
        self.test_case.assert_element(
            f"{self.MEMBER_ROW_XPATH}[{new_row_order}]", by=By.XPATH
        )
        return new_row_order

    def do_delete_member(self, row_order: int) -> None:
        self.test_case.click_xpath(
            f"{self.MEMBER_ROW_XPATH}[{row_order}]"
            "//*[@data-testid='sysml-delete-member-action']"
        )
        self.test_case.assert_attribute(
            f"{self.MEMBER_ROW_XPATH}[{row_order}]",
            "deleted",
            by=By.XPATH,
        )

    def do_fill_in_source(self, source: str) -> None:
        self.do_open_tab("Source")
        self.do_fill_in("sysml-source", source)


class Form_EditSysMLSource(Form):  # pylint: disable=invalid-name
    """The editor of the whole SysML source of a design package."""

    @staticmethod
    def open_for_document(test_case: E2ECase):
        root_xpath = "//sdoc-node[@data-testid='node-root']"
        test_case.hover_and_click(
            hover_selector=root_xpath,
            click_selector=(
                f"{root_xpath}"
                "//*[@data-testid='document-edit-sysml-source-action']"
            ),
            hover_by=By.XPATH,
            click_by=By.XPATH,
        )
        test_case.assert_element(
            "//*[@data-testid='form-field-sysml-source']", by=By.XPATH
        )
        return Form_EditSysMLSource(test_case)

    def do_fill_in_source(self, source: str) -> None:
        self.do_fill_in("sysml-source", source)
