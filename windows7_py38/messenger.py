from __future__ import annotations

import atexit
import logging
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scraper import Listing


LOGGER = logging.getLogger(__name__)
LOGIN_URL = "https://id.kolesa.kz/login/?destination=https%3A%2F%2Fkrisha.kz%2Fmy"
DEFAULT_TIMEOUT_MS = 45_000
DEFAULT_SETTLE_MS = 1_200
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/109.0.0.0 Safari/537.36"
)

# Text patterns for Selenium element lookup. Update here if krisha changes labels.
_WRITE_MSG_TEXTS = ["Написать сообщение", "Написать продавцу"]
_SEND_BTN_TEXTS = ["Отправить", "Отправить сообщение"]
_DISMISS_OVERLAY_TEXTS = [
    "Скрыть подсказку",
    "Закрыть подсказку",
    "Понятно",
    "Закрыть",
]
_LOGIN_SUBMIT_TEXTS = ["Войти", "Вход", "Продолжить", "Далее"]
_CHAT_URL_TOKENS = ("/my/messages", "/messages", "/messenger", "/chat")


def _resolve_chromedriver_path() -> str:
    configured = os.getenv("KRISHA_CHROMEDRIVER", "").strip().strip('"')
    if configured:
        return configured
    local_driver = Path(__file__).resolve().parent / "chromedriver.exe"
    if local_driver.exists():
        return str(local_driver)
    found = shutil.which("chromedriver")
    return found or ""


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "y", "да"}


def _xpath_literal(text: str) -> str:
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    parts = text.split("'")
    return "concat(" + ', "\'", '.join(f"'{part}'" for part in parts) + ")"


@dataclass(frozen=True)
class MessageResult:
    listing_id: str
    status: str
    response: str = ""
    chat_url: str = ""


class KrishaMessenger:
    def __init__(
        self,
        login: str = "",
        password: str = "",
        headless: bool | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        settle_ms: int = DEFAULT_SETTLE_MS,
    ) -> None:
        self.login = login.strip()
        self.password = password
        self.headless = _env_flag("KRISHA_HEADLESS", True) if headless is None else bool(headless)
        self.timeout_ms = max(10_000, int(timeout_ms))
        self.timeout_sec = self.timeout_ms / 1000
        self.settle_ms = max(0, int(settle_ms))
        self.profile_dir = Path(os.getenv("KRISHA_CHROME_PROFILE_DIR", ".krisha_chrome_profile").strip()).resolve()

        self._driver: WebDriver | None = None
        atexit.register(self.close)

    def send_message(self, listing: Listing, message: str, dry_run: bool = True) -> MessageResult:
        if dry_run:
            return MessageResult(
                listing_id=listing.listing_id,
                status="dry_run",
                response="Message was not sent because dry-run mode is active.",
            )

        try:
            page = self._driver_page()
            self._open_listing(page, listing.url)

            if not self._click_write_message(page, listing_id=listing.listing_id):
                return MessageResult(
                    listing_id=listing.listing_id,
                    status="skipped_no_chat",
                    response="Message button was not found on listing page.",
                )

            if self._has_auth_gate(page):
                self._open_login_from_auth_gate(page)

            if self._is_login_page(page):
                login_error = self._perform_login(page)
                if login_error:
                    return MessageResult(
                        listing_id=listing.listing_id,
                        status="failed",
                        response=login_error,
                    )
                self._open_listing(page, listing.url)
                if not self._click_write_message(page, listing_id=listing.listing_id):
                    return MessageResult(
                        listing_id=listing.listing_id,
                        status="skipped_no_chat",
                        response="Failed to reopen message form after login.",
                    )

            if any(token in page.current_url for token in _CHAT_URL_TOKENS):
                self._wait_for_chat_editor(page)

            editor = self._find_message_editor(page)
            if editor is None:
                return MessageResult(
                    listing_id=listing.listing_id,
                    status="failed",
                    response="Message editor was not found after opening message form.",
                )

            self._fill_editor(page, editor, message)
            if not self._click_send_button(page):
                return MessageResult(
                    listing_id=listing.listing_id,
                    status="failed",
                    response="Send button was not found in message form.",
                )

            self._wait_ms(self.settle_ms)
            chat_url = self._extract_chat_url(page)
            send_confirmed = self._verify_send(page, editor, expected_message=message)
            if not send_confirmed:
                return MessageResult(
                    listing_id=listing.listing_id,
                    status="failed",
                    response="Send button was clicked but message delivery could not be confirmed.",
                    chat_url=chat_url,
                )
            return MessageResult(
                listing_id=listing.listing_id,
                status="sent",
                response="Message submitted via browser automation.",
                chat_url=chat_url,
            )
        except Exception as exc:
            LOGGER.exception("Failed to send Krisha message listing_id=%s", listing.listing_id)
            return MessageResult(
                listing_id=listing.listing_id,
                status="failed",
                response=str(exc),
            )

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def _driver_page(self) -> WebDriver:
        if self._driver is None:
            self._driver = self._create_driver()
        return self._driver

    def _create_driver(self) -> WebDriver:
        return self._create_driver_with_profile(self.profile_dir, allow_fallback=True)

    def _create_driver_with_profile(self, profile_dir: Path, allow_fallback: bool) -> WebDriver:
        profile_dir.mkdir(parents=True, exist_ok=True)
        options = Options()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=ru-RU")
        options.add_argument("--window-size=1365,900")
        options.add_argument(f"--user-agent={DEFAULT_USER_AGENT}")
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        if self.headless:
            options.add_argument("--headless")

        chrome_binary = os.getenv("KRISHA_CHROME_BINARY", "").strip()
        if chrome_binary:
            options.binary_location = chrome_binary

        driver_path = _resolve_chromedriver_path()
        service = Service(executable_path=driver_path) if driver_path else Service()
        try:
            driver = webdriver.Chrome(service=service, options=options)
        except WebDriverException as exc:
            if allow_fallback and self._is_profile_start_error(exc):
                fallback_profile = Path(tempfile.mkdtemp(prefix="krisha-chrome-profile-"))
                LOGGER.warning(
                    "Chrome failed to start with profile %s; retrying with temporary profile %s",
                    profile_dir,
                    fallback_profile,
                )
                return self._create_driver_with_profile(fallback_profile, allow_fallback=False)
            hint = (
                "Chrome/ChromeDriver could not start. On Windows 7 use Chrome 109 "
                "and set KRISHA_CHROMEDRIVER to the matching chromedriver.exe path "
                "if Selenium Manager cannot download it automatically."
            )
            raise RuntimeError(f"{hint} Original error: {exc}") from exc

        driver.set_page_load_timeout(self.timeout_sec)
        driver.implicitly_wait(0)
        return driver

    @staticmethod
    def _is_profile_start_error(exc: WebDriverException) -> bool:
        text = str(exc)
        return "DevToolsActivePort" in text or "Chrome failed to start" in text

    def _open_listing(self, page: WebDriver, listing_url: str) -> None:
        page.get(listing_url)
        self._wait_ms(self.settle_ms)
        self._dismiss_page_overlays(page)
        if self._is_login_page(page):
            login_error = self._perform_login(page)
            if login_error:
                raise RuntimeError(login_error)
            page.get(listing_url)
            self._wait_ms(self.settle_ms)
            self._dismiss_page_overlays(page)

    def _dismiss_page_overlays(self, page: WebDriver) -> None:
        try:
            for text in _DISMISS_OVERLAY_TEXTS:
                for button in self._elements_by_text(page, ("button", "a"), text):
                    if self._click_element(page, button, timeout_sec=1.5):
                        self._wait_ms(min(600, self.settle_ms))
            page.execute_script(
                """
                const el = document.querySelector('#overlay-tutorial');
                if (!el) return;
                el.style.display = 'none';
                el.style.pointerEvents = 'none';
                el.classList.remove('tutorial__cover--visible');
                """
            )
        except Exception:
            pass

    def _is_login_page(self, page: WebDriver) -> bool:
        current_url = self._current_url(page).lower()
        if "id.kolesa.kz/login" in current_url:
            return True
        return self._first_visible(page, By.CSS_SELECTOR, "input[name='login']") is not None

    def _has_auth_gate(self, page: WebDriver) -> bool:
        if self._is_login_page(page):
            return True
        if self._first_visible_by_text(page, ("button", "a"), "Войти") is not None:
            return True
        if self._first_visible_by_text(page, ("button", "a"), "Зарегистрироваться") is not None:
            return True
        return False

    def _open_login_from_auth_gate(self, page: WebDriver) -> None:
        candidates = [
            self._first_visible_by_text(page, ("button", "a"), "Войти"),
            self._first_visible(page, By.CSS_SELECTOR, "button[type='submit']"),
        ]
        for candidate in candidates:
            if candidate is not None and self._click_element(page, candidate):
                self._wait_ms(self.settle_ms)
                return

    def _perform_login(self, page: WebDriver) -> str | None:
        if not self.login or not self.password:
            return "KRISHA_LOGIN/KRISHA_PASSWORD are required for --send mode."

        if not self._is_login_page(page):
            page.get(LOGIN_URL)
            self._wait_ms(self.settle_ms)
            if not self._is_login_page(page):
                return None

        try:
            login_input = WebDriverWait(page, self.timeout_sec).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='login']"))
            )
            login_input.clear()
            login_input.send_keys(self.login)

            password_input = self._first_visible(page, By.CSS_SELECTOR, "input[name='password']")
            if password_input is None:
                if not self._click_login_submit(page):
                    return "Login submit button was not found (step 1)."
                try:
                    password_input = WebDriverWait(page, self.timeout_sec).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='password']"))
                    )
                except TimeoutException:
                    password_input = None

            if password_input is None:
                return "Password field did not appear after phone submit (possible captcha/2FA)."

            password_input.clear()
            password_input.send_keys(self.password)
            if not self._click_login_submit(page):
                return "Login submit button was not found (step 2)."
        except TimeoutException:
            return "Krisha login form did not load in time."
        except Exception as exc:
            return f"Krisha login error: {exc}"

        for _ in range(20):
            if not self._is_login_page(page):
                return None
            self._wait_ms(1000)
        return "Krisha login did not complete (possible captcha or wrong credentials)."

    def _click_login_submit(self, page: WebDriver) -> bool:
        candidates = []
        for text in _LOGIN_SUBMIT_TEXTS:
            candidates.extend(self._elements_by_text(page, ("button", "input"), text))
        candidates.extend(self._visible_elements(page, By.CSS_SELECTOR, "button[type='submit'],input[type='submit']"))
        return self._click_first(page, candidates)

    def _click_write_message(self, page: WebDriver, listing_id: str = "") -> bool:
        candidates: list[WebElement] = []
        if listing_id:
            candidates.extend(self._visible_elements(page, By.CSS_SELECTOR, f"a[href*='advertId={listing_id}']"))
        candidates.extend(self._visible_elements(page, By.CSS_SELECTOR, "a[href*='advertId=']"))
        for text in _WRITE_MSG_TEXTS:
            candidates.extend(self._elements_by_text(page, ("button", "a"), text))
        candidates.extend(
            self._visible_elements(
                page,
                By.CSS_SELECTOR,
                "button[data-type*='message'],button[aria-label*='сообщ'],button[aria-label*='написать']",
            )
        )

        for candidate in candidates:
            href = self._attribute(candidate, "href")
            if "openSupportThread" in href:
                continue
            if self._click_element(page, candidate, timeout_sec=3):
                self._wait_ms(self.settle_ms)
                return True
        return False

    def _wait_for_chat_editor(self, page: WebDriver, extra_ms: int = 4000) -> None:
        try:
            WebDriverWait(page, extra_ms / 1000).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "[contenteditable='true'], textarea"))
            )
        except Exception:
            self._wait_ms(self.settle_ms)

    def _find_message_editor(self, page: WebDriver) -> WebElement | None:
        selectors = [
            "[contenteditable='true']",
            "textarea[name*='message']",
            "textarea[placeholder*='общ']",
            "textarea",
            "[role='textbox']",
        ]
        for selector in selectors:
            element = self._first_visible(page, By.CSS_SELECTOR, selector)
            if element is not None:
                return element
        return None

    def _fill_editor(self, page: WebDriver, editor: WebElement, message: str) -> None:
        tag_name = self._tag_name(editor)
        if tag_name in {"textarea", "input"}:
            editor.clear()
            editor.send_keys(message)
            return

        editor.click()
        editor.send_keys(Keys.CONTROL, "a")
        editor.send_keys(Keys.BACKSPACE)
        editor.send_keys(message)

    def _click_send_button(self, page: WebDriver) -> bool:
        candidates: list[WebElement] = []
        for text in _SEND_BTN_TEXTS:
            candidates.extend(self._elements_by_text(page, ("button", "input"), text))
        candidates.extend(
            self._visible_elements(
                page,
                By.CSS_SELECTOR,
                "input[type='submit'][value*='Отправ'],button[type='submit'],button[aria-label*='отправ']",
            )
        )
        return self._click_first(page, candidates, timeout_sec=3)

    def _verify_send(self, page, editor, expected_message: str = "") -> bool:  # noqa: ANN001
        """Return True if we can confirm the message was delivered."""
        try:
            if not self._element_visible(editor):
                return True
        except Exception:
            return True

        success_selectors = [
            "[class*='success']",
            "[class*='sent']",
            "[class*='delivered']",
        ]
        for selector in success_selectors:
            if self._first_visible_compatible(page, selector) is not None:
                return True

        value = self._element_value_or_text(editor)
        if value.strip():
            LOGGER.warning("Send verification: editor still contains text after send click")
            return False

        if expected_message.strip():
            try:
                body_text = page.find_element(By.TAG_NAME, "body").text
                if expected_message.strip() in body_text:
                    return True
            except Exception:
                pass

        return True

    def _extract_chat_url(self, page: WebDriver) -> str:
        current = self._current_url(page).strip()
        if any(token in current for token in _CHAT_URL_TOKENS):
            return current

        link = self._first_visible(page, By.CSS_SELECTOR, "a[href*='message'],a[href*='chat']")
        if link is not None:
            href = self._attribute(link, "href")
            if href:
                return urljoin(current, href)
        return ""

    def _visible_elements(self, page: WebDriver, by: str, selector: str) -> list[WebElement]:
        try:
            return [element for element in page.find_elements(by, selector) if self._element_visible(element)]
        except Exception:
            return []

    def _first_visible(self, page: WebDriver, by: str, selector: str) -> WebElement | None:
        elements = self._visible_elements(page, by, selector)
        return elements[0] if elements else None

    def _elements_by_text(self, page: WebDriver, tags: Iterable[str], text: str) -> list[WebElement]:
        tag_expr = " or ".join(f"self::{tag}" for tag in tags)
        text_literal = _xpath_literal(text)
        xpath = f"//*[{tag_expr}][contains(normalize-space(.), {text_literal}) or contains(@value, {text_literal})]"
        return self._visible_elements(page, By.XPATH, xpath)

    def _first_visible_by_text(self, page: WebDriver, tags: Iterable[str], text: str) -> WebElement | None:
        elements = self._elements_by_text(page, tags, text)
        return elements[0] if elements else None

    def _click_first(self, page: WebDriver, candidates: Iterable[WebElement], timeout_sec: float = 3) -> bool:
        for candidate in candidates:
            if self._click_element(page, candidate, timeout_sec=timeout_sec):
                return True
        return False

    def _click_element(self, page: WebDriver, element: WebElement, timeout_sec: float = 3) -> bool:
        try:
            if not self._element_visible(element):
                return False
            page.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
            WebDriverWait(page, timeout_sec).until(lambda _: element.is_enabled())
            try:
                element.click()
            except Exception:
                page.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False

    def _first_visible_compatible(self, page, selector: str):  # noqa: ANN001
        if hasattr(page, "find_elements"):
            return self._first_visible(page, By.CSS_SELECTOR, selector)
        if hasattr(page, "locator"):
            try:
                item = page.locator(selector).first
                return item if self._element_visible(item) else None
            except Exception:
                try:
                    item = page.locator(selector)
                    return item if self._element_visible(item) else None
                except Exception:
                    return None
        return None

    @staticmethod
    def _attribute(element, name: str) -> str:  # noqa: ANN001
        try:
            return element.get_attribute(name) or ""
        except Exception:
            return ""

    @staticmethod
    def _current_url(page) -> str:  # noqa: ANN001
        return str(getattr(page, "current_url", getattr(page, "url", "")) or "")

    @staticmethod
    def _element_visible(element) -> bool:  # noqa: ANN001
        if hasattr(element, "is_displayed"):
            return bool(element.is_displayed())
        if hasattr(element, "is_visible"):
            return bool(element.is_visible())
        return False

    @staticmethod
    def _tag_name(element) -> str:  # noqa: ANN001
        try:
            return str(getattr(element, "tag_name", "") or "").lower()
        except Exception:
            return ""

    def _element_value_or_text(self, element) -> str:  # noqa: ANN001
        tag_name = self._tag_name(element)
        try:
            if tag_name in {"textarea", "input"}:
                return element.get_attribute("value") or ""
        except Exception:
            pass
        try:
            return element.text or ""
        except Exception:
            pass
        try:
            evaluated = str(element.evaluate("el => el.tagName"))
            if evaluated.upper() in {"TEXTAREA", "INPUT"} and hasattr(element, "input_value"):
                return element.input_value()
            if hasattr(element, "inner_text"):
                return element.inner_text()
        except Exception:
            pass
        return ""

    @staticmethod
    def _wait_ms(ms: int) -> None:
        if ms > 0:
            time.sleep(ms / 1000)
