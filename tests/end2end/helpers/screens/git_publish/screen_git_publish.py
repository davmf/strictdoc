from selenium.webdriver.common.by import By
from seleniumbase import BaseCase

from tests.end2end.helpers.screens.screen import Screen

XPATH_BADGE = '//*[@data-testid="git-publish-badge"]'


class Screen_GitPublish(Screen):  # pylint: disable=invalid-name
    """
    The "Changes since last publish" screen and its navigation bar badge.
    """

    def __init__(self, test_case: BaseCase) -> None:
        super().__init__(test_case)

    # Badge. The badge is in the navigation bar of every server screen.

    def assert_badge_text(self, text: str) -> None:
        self.test_case.assert_element(
            f'{XPATH_BADGE}[@title="{text}"]', by=By.XPATH
        )

    def do_click_on_badge(self) -> "Screen_GitPublish":
        self.test_case.click_xpath(XPATH_BADGE)
        self.assert_on_screen()
        return self

    # Screen.

    def assert_on_screen(self) -> None:
        super().assert_on_screen("git-publish")
        self.test_case.assert_element(
            '//*[@data-testid="git-publish-screen"]', by=By.XPATH
        )

    def assert_summary(self, text: str) -> None:
        self.assert_xpath_contains(
            '//*[@data-testid="git-publish-summary"]', text
        )

    def assert_unavailable(self) -> None:
        self.assert_xpath_contains(
            '//*[@data-testid="git-publish-unavailable"]',
            "Publishing is unavailable: "
            "this project is not in a Git repository",
        )

    def assert_change(self, path: str, display_name: str, kind: str) -> None:
        xpath_to_change = self._get_xpath_to_change(path)
        self.test_case.assert_element(
            f'{xpath_to_change}[@data-kind="{kind}"]'
            '//*[@data-testid="git-publish-change-name"]'
            f'[contains(., "{display_name}")]',
            by=By.XPATH,
        )

    def assert_no_change(self, path: str) -> None:
        self.test_case.assert_element_not_present(
            self._get_xpath_to_change(path), by=By.XPATH
        )

    def assert_view_changes_link(self, path: str) -> None:
        self.test_case.assert_element(
            self._get_xpath_to_change(path)
            + '//*[@data-testid="git-publish-view-changes-action"]',
            by=By.XPATH,
        )

    def do_discard_change(self, path: str, confirm_message: str) -> None:
        self.test_case.click_xpath(
            self._get_xpath_to_change(path)
            + '//*[@data-testid="git-publish-discard-action"]'
        )
        self.assert_xpath_contains(
            '//*[@data-testid="confirm-message"]', confirm_message
        )
        self.test_case.click_xpath('//*[@data-testid="confirm-action"]')
        self.assert_no_change(path)

    @staticmethod
    def _get_xpath_to_change(path: str) -> str:
        return f'//*[@data-testid="git-publish-change"][@data-path="{path}"]'
