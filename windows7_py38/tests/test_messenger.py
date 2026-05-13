from __future__ import annotations

from messenger import KrishaMessenger, _resolve_chromedriver_path
from scraper import Listing
from selenium.common.exceptions import WebDriverException


class _InvisibleLocator:
    def is_visible(self) -> bool:
        return False


class _FakePage:
    url = "https://krisha.kz/my/messages/?advertId=123#/"

    def locator(self, selector: str):  # noqa: ANN001
        return _InvisibleLocator()


class _EditorWithText:
    def is_visible(self) -> bool:
        return True

    def evaluate(self, script: str) -> str:  # noqa: ARG002
        return "DIV"

    def inner_text(self) -> str:
        return "Здравствуйте"


def test_verify_send_does_not_treat_chat_url_as_success_when_editor_still_has_text() -> None:
    messenger = KrishaMessenger()

    assert messenger._verify_send(_FakePage(), _EditorWithText(), expected_message="Здравствуйте") is False


def test_dry_run_does_not_start_selenium_driver() -> None:
    listing = Listing(
        listing_id="123",
        title="2-комнатная квартира",
        price="10 000 000 ₸",
        district="Караганда",
        url="https://krisha.kz/a/show/123",
        category="prodazha",
    )
    messenger = KrishaMessenger()

    result = messenger.send_message(listing, "Здравствуйте", dry_run=True)

    assert result.status == "dry_run"
    assert messenger._driver is None


def test_real_send_path_fills_editor_clicks_send_and_returns_sent() -> None:
    listing = Listing(
        listing_id="123",
        title="2-комнатная квартира",
        price="10 000 000 тг",
        district="Караганда",
        url="https://krisha.kz/a/show/123",
        category="prodazha",
    )

    class FakePage:
        current_url = "https://krisha.kz/my/messages/?advertId=123#/"

    class FakeEditor:
        pass

    class FakeMessenger(KrishaMessenger):
        def __init__(self) -> None:
            super().__init__(settle_ms=0)
            self.calls: list[str] = []
            self.page = FakePage()
            self.editor = FakeEditor()
            self.filled_message = ""

        def _driver_page(self):  # noqa: ANN001
            self.calls.append("driver")
            return self.page

        def _open_listing(self, page, listing_url: str) -> None:  # noqa: ANN001
            self.calls.append(f"open:{listing_url}")

        def _click_write_message(self, page, listing_id: str = "") -> bool:  # noqa: ANN001
            self.calls.append(f"write:{listing_id}")
            return True

        def _has_auth_gate(self, page) -> bool:  # noqa: ANN001
            return False

        def _is_login_page(self, page) -> bool:  # noqa: ANN001
            return False

        def _wait_for_chat_editor(self, page, extra_ms: int = 4000) -> None:  # noqa: ANN001
            self.calls.append("wait-editor")

        def _find_message_editor(self, page):  # noqa: ANN001
            self.calls.append("find-editor")
            return self.editor

        def _fill_editor(self, page, editor, message: str) -> None:  # noqa: ANN001
            self.calls.append("fill")
            self.filled_message = message

        def _click_send_button(self, page) -> bool:  # noqa: ANN001
            self.calls.append("click-send")
            return True

        def _extract_chat_url(self, page) -> str:  # noqa: ANN001
            return page.current_url

        def _verify_send(self, page, editor, expected_message: str = "") -> bool:  # noqa: ANN001
            self.calls.append(f"verify:{expected_message}")
            return True

    messenger = FakeMessenger()

    result = messenger.send_message(listing, "Здравствуйте", dry_run=False)

    assert result.status == "sent"
    assert result.chat_url == "https://krisha.kz/my/messages/?advertId=123#/"
    assert messenger.filled_message == "Здравствуйте"
    assert "click-send" in messenger.calls
    assert messenger.calls.index("fill") < messenger.calls.index("click-send") < messenger.calls.index("verify:Здравствуйте")


def test_chrome_profile_start_failure_retries_with_temporary_profile(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    class FakeDriver:
        def __init__(self) -> None:
            self.page_load_timeout = None
            self.implicit_wait_timeout = None

        def set_page_load_timeout(self, timeout) -> None:  # noqa: ANN001
            self.page_load_timeout = timeout

        def implicitly_wait(self, timeout) -> None:  # noqa: ANN001
            self.implicit_wait_timeout = timeout

    calls = []
    fake_driver = FakeDriver()

    def fake_chrome(service, options):  # noqa: ANN001
        profile_args = [arg for arg in options.arguments if arg.startswith("--user-data-dir=")]
        calls.append(profile_args[0] if profile_args else "")
        if len(calls) == 1:
            raise WebDriverException("Chrome failed to start: DevToolsActivePort file doesn't exist")
        return fake_driver

    monkeypatch.setenv("KRISHA_CHROME_PROFILE_DIR", str(tmp_path / "persistent-profile"))
    monkeypatch.setattr("messenger.webdriver.Chrome", fake_chrome)

    messenger = KrishaMessenger(timeout_ms=12_000)
    driver = messenger._create_driver()

    assert driver is fake_driver
    assert len(calls) == 2
    assert "persistent-profile" in calls[0]
    assert "krisha-chrome-profile-" in calls[1]
    assert fake_driver.page_load_timeout == 12
    assert fake_driver.implicit_wait_timeout == 0


def test_chromedriver_resolves_local_file_when_env_is_empty(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    fake_module = tmp_path / "messenger.py"
    fake_module.write_text("", encoding="utf-8")
    fake_driver = tmp_path / "chromedriver.exe"
    fake_driver.write_text("", encoding="utf-8")

    monkeypatch.delenv("KRISHA_CHROMEDRIVER", raising=False)
    monkeypatch.setattr("messenger.__file__", str(fake_module))
    monkeypatch.setattr("messenger.shutil.which", lambda name: None)

    assert _resolve_chromedriver_path() == str(fake_driver)
