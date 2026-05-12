from __future__ import annotations

import atexit
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from scraper import Listing


LOGGER = logging.getLogger(__name__)
LOGIN_URL = "https://id.kolesa.kz/login/?destination=https%3A%2F%2Fkrisha.kz%2Fmy"
DEFAULT_TIMEOUT_MS = 45_000
DEFAULT_SETTLE_MS = 1_200

# Text patterns for Playwright locators — update here if krisha changes button labels.
_WRITE_MSG_TEXTS = ["Написать сообщение", "Написать", "Написать продавцу"]
_SEND_BTN_TEXTS = ["Отправить", "Отправить сообщение"]
_DISMISS_OVERLAY_TEXTS = [
    "Скрыть подсказку",
    "Закрыть подсказку",
    "Понятно",
    "Закрыть",
]
_LOGIN_SUBMIT_TEXTS = ["Войти", "Вход", "Продолжить", "Далее"]
_CHAT_URL_TOKENS = ("/my/messages", "/messages", "/messenger", "/chat")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "y", "да"}


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
        self.settle_ms = max(0, int(settle_ms))
        self.storage_state_path = Path(os.getenv("KRISHA_STORAGE_STATE_FILE", ".krisha_storage_state.json").strip())

        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        atexit.register(self.close)

    def send_message(self, listing: Listing, message: str, dry_run: bool = True) -> MessageResult:
        if dry_run:
            return MessageResult(
                listing_id=listing.listing_id,
                status="dry_run",
                response="Message was not sent because dry-run mode is active.",
            )
        page: Page | None = None
        try:
            page = self._new_page()
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

            # When logged in, "Написать сообщение" is a link that navigates to
            # /my/messages/?advertId=... (SPA). Wait for the chat to finish loading.
            if any(token in page.url for token in _CHAT_URL_TOKENS):
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

            if self.settle_ms:
                page.wait_for_timeout(self.settle_ms)
            self._save_storage_state()
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
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def _ensure_context(self) -> BrowserContext:
        if self._context is not None:
            return self._context
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        if self._browser is None:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-gpu", "--no-sandbox"],
            )

        context_kwargs: dict[str, Any] = {
            "locale": "ru-RU",
            "viewport": {"width": 1365, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
        }
        if self.storage_state_path.exists():
            context_kwargs["storage_state"] = str(self.storage_state_path)

        self._context = self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(self.timeout_ms)
        return self._context

    def _save_storage_state(self) -> None:
        if self._context is None:
            return
        try:
            self._context.storage_state(path=str(self.storage_state_path))
        except Exception as exc:
            LOGGER.info("Failed to persist storage state for Krisha session: %s", exc)

    def _new_page(self) -> Page:
        context = self._ensure_context()
        page = context.new_page()
        page.set_default_timeout(self.timeout_ms)
        return page

    def _open_listing(self, page: Page, listing_url: str) -> None:
        page.goto(listing_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        if self.settle_ms:
            page.wait_for_timeout(self.settle_ms)
        self._dismiss_page_overlays(page)
        if self._is_login_page(page):
            login_error = self._perform_login(page)
            if login_error:
                raise RuntimeError(login_error)
            page.goto(listing_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            if self.settle_ms:
                page.wait_for_timeout(self.settle_ms)
            self._dismiss_page_overlays(page)

    def _dismiss_page_overlays(self, page: Page) -> None:
        try:
            for text in _DISMISS_OVERLAY_TEXTS:
                btn = page.locator(f"button:has-text('{text}')")
                count = btn.count()
                for idx in range(count):
                    item = btn.nth(idx)
                    if item.is_visible():
                        try:
                            item.click(timeout=1500)
                            if self.settle_ms:
                                page.wait_for_timeout(min(600, self.settle_ms))
                        except Exception:
                            pass
            page.evaluate(
                """
                () => {
                    const el = document.querySelector('#overlay-tutorial');
                    if (!el) return;
                    el.style.display = 'none';
                    el.style.pointerEvents = 'none';
                    el.classList.remove('tutorial__cover--visible');
                }
                """
            )
        except Exception:
            pass

    def _is_login_page(self, page: Page) -> bool:
        current_url = page.url.lower()
        if "id.kolesa.kz/login" in current_url:
            return True
        try:
            login_visible = page.locator("input[name='login']").first.is_visible()
            return bool(login_visible)
        except Exception:
            return False

    def _has_auth_gate(self, page: Page) -> bool:
        if self._is_login_page(page):
            return True
        try:
            login_btn = page.get_by_role("button", name=re.compile(r"^войти$", re.IGNORECASE)).first
            if login_btn.is_visible():
                return True
        except Exception:
            pass
        try:
            signup_btn = page.get_by_role(
                "button", name=re.compile(r"зарегистрироваться", re.IGNORECASE)
            ).first
            if signup_btn.is_visible():
                return True
        except Exception:
            pass
        return False

    def _open_login_from_auth_gate(self, page: Page) -> None:
        candidates = [
            page.get_by_role("button", name=re.compile(r"^войти$", re.IGNORECASE)).first,
            page.locator("button:has-text('Войти')").first,
            page.locator("a:has-text('Войти')").first,
        ]
        for candidate in candidates:
            try:
                if candidate.is_visible():
                    candidate.click()
                    if self.settle_ms:
                        page.wait_for_timeout(self.settle_ms)
                    return
            except Exception:
                continue

    def _perform_login(self, page: Page) -> str | None:
        if not self.login or not self.password:
            return "KRISHA_LOGIN/KRISHA_PASSWORD are required for --send mode."

        if not self._is_login_page(page):
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
            if self.settle_ms:
                page.wait_for_timeout(self.settle_ms)

        try:
            login_input = page.locator("input[name='login']").first
            login_input.wait_for(state="visible", timeout=self.timeout_ms)
            login_input.fill(self.login)

            password_input = page.locator("input[name='password']").first
            password_visible = False
            try:
                password_visible = password_input.is_visible()
            except Exception:
                password_visible = False

            if not password_visible:
                if not self._click_login_submit(page):
                    return "Login submit button was not found (step 1)."
                try:
                    password_input.wait_for(state="visible", timeout=self.timeout_ms)
                    password_visible = True
                except Exception:
                    password_visible = False

            if not password_visible:
                return "Password field did not appear after phone submit (possible captcha/2FA)."

            password_input.fill(self.password)
            if not self._click_login_submit(page):
                return "Login submit button was not found (step 2)."
        except PlaywrightTimeoutError:
            return "Krisha login form did not load in time."
        except Exception as exc:
            return f"Krisha login error: {exc}"

        for _ in range(20):
            if not self._is_login_page(page):
                self._save_storage_state()
                return None
            page.wait_for_timeout(1000)
        return "Krisha login did not complete (possible captcha or wrong credentials)."

    def _click_login_submit(self, page: Page) -> bool:
        pattern = re.compile("|".join(_LOGIN_SUBMIT_TEXTS), re.IGNORECASE)
        submit_candidates = [
            page.get_by_role("button", name=pattern).first,
            page.locator("button[type='submit']").first,
            page.locator("input[type='submit']").first,
            *[page.locator(f"button:has-text('{t}')").first for t in _LOGIN_SUBMIT_TEXTS],
            page.locator("input[value*='Вход']").first,
        ]
        for candidate in submit_candidates:
            try:
                if candidate.is_visible():
                    candidate.click()
                    if self.settle_ms:
                        page.wait_for_timeout(self.settle_ms)
                    return True
            except Exception:
                continue
        return False

    def _click_write_message(self, page: Page, listing_id: str = "") -> bool:
        # Build candidate list in priority order. The most reliable signal is
        # an advertId link — present when the seller allows messaging.
        # Deliberately exclude support/service links (openSupportThread) and
        # the bare "Написать" text (too broad — matches support sidebar link).
        candidates = []

        if listing_id:
            candidates.append(page.locator(f"a[href*='advertId={listing_id}']"))
        candidates += [
            page.locator("a[href*='advertId=']"),
            page.get_by_role("button", name=re.compile(r"Написать сообщение|Написать продавцу", re.IGNORECASE)),
            page.get_by_role("link", name=re.compile(r"Написать сообщение|Написать продавцу", re.IGNORECASE)),
            page.locator("button:has-text('Написать сообщение')"),
            page.locator("button:has-text('Написать продавцу')"),
            page.locator("a:has-text('Написать сообщение')"),
            page.locator("a:has-text('Написать продавцу')"),
            page.locator("button[data-type*='message']"),
            page.locator("button[aria-label*='сообщ']"),
            page.locator("button[aria-label*='написать']"),
        ]
        for candidate in candidates:
            count = candidate.count()
            for idx in range(count):
                try:
                    item = candidate.nth(idx)
                    if not item.is_visible():
                        continue
                    href = ""
                    try:
                        href = item.get_attribute("href") or ""
                    except Exception:
                        pass
                    # Skip support / service links
                    if "openSupportThread" in href:
                        continue
                    try:
                        item.click(timeout=3000)
                    except Exception:
                        self._dismiss_page_overlays(page)
                        item.click(timeout=3000, force=True)
                    if self.settle_ms:
                        page.wait_for_timeout(self.settle_ms)
                    return True
                except Exception:
                    continue
        return False

    def _wait_for_chat_editor(self, page: Page, extra_ms: int = 4000) -> None:
        """Wait for SPA chat editor to appear after navigating to /my/messages/."""
        try:
            page.wait_for_selector(
                "[contenteditable='true'], textarea",
                state="visible",
                timeout=extra_ms,
            )
        except Exception:
            if self.settle_ms:
                page.wait_for_timeout(self.settle_ms)

    def _find_message_editor(self, page: Page):
        candidates = [
            page.locator("[contenteditable='true']").first,
            page.locator("textarea[name*='message']").first,
            page.locator("textarea[placeholder*='общ']").first,
            page.get_by_role("textbox", name=re.compile(r"сообщ", re.IGNORECASE)).first,
            page.locator("textarea").first,
        ]
        for candidate in candidates:
            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                continue
        return None

    def _fill_editor(self, page: Page, editor, message: str) -> None:
        try:
            tag_name = str(editor.evaluate("el => (el.tagName || '').toLowerCase()"))
        except Exception:
            tag_name = ""

        if tag_name in {"textarea", "input"}:
            editor.fill(message)
            return

        editor.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(message, delay=8)

    def _click_send_button(self, page: Page) -> bool:
        pattern = re.compile("|".join(_SEND_BTN_TEXTS), re.IGNORECASE)
        candidates = [
            page.get_by_role("button", name=pattern),
            *[page.locator(f"button:has-text('{t}')") for t in _SEND_BTN_TEXTS],
            page.locator("input[type='submit'][value*='Отправ']"),
            page.locator("button[type='submit']"),
            page.locator("button[aria-label*='отправ']"),
        ]
        for candidate in candidates:
            count = candidate.count()
            for idx in range(count):
                try:
                    item = candidate.nth(idx)
                    if item.is_visible():
                        try:
                            item.click(timeout=3000)
                        except Exception:
                            self._dismiss_page_overlays(page)
                            item.click(timeout=3000, force=True)
                        return True
                except Exception:
                    continue
        return False

    def _verify_send(self, page: Page, editor, expected_message: str = "") -> bool:
        """Return True if we can confirm the message was delivered."""
        # 1. The editor is gone (modal form closed after send).
        try:
            if not editor.is_visible():
                return True
        except Exception:
            return True  # element detached — form closed

        # 2. A success/confirmation element appeared.
        success_selectors = [
            "[class*='success']",
            "[class*='sent']",
            "[class*='delivered']",
            "div:has-text('Сообщение отправлено')",
            "div:has-text('Ваше сообщение')",
        ]
        for sel in success_selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    return True
            except Exception:
                continue

        # 3. Editor is still visible and non-empty — likely not sent.
        try:
            value = editor.input_value() if editor.evaluate("el => el.tagName") in ("TEXTAREA", "INPUT") else editor.inner_text()
            if value.strip():
                LOGGER.warning("Send verification: editor still contains text after send click")
                return False
        except Exception:
            pass

        # 4. SPA chats keep the URL on /my/messages both before and after send.
        # Confirm that the input cleared, and when possible that the message text
        # is now present in the conversation body.
        if expected_message.strip():
            try:
                body_text = page.locator("body").inner_text(timeout=1500)
                if expected_message.strip() in body_text:
                    return True
            except Exception:
                pass

        return True  # input cleared and no counter-evidence

    def _extract_chat_url(self, page: Page) -> str:
        current = page.url.strip()
        if any(token in current for token in _CHAT_URL_TOKENS):
            return current

        try:
            link = page.locator("a[href*='message'],a[href*='chat']").first
            if link.is_visible():
                href = link.get_attribute("href") or ""
                if href:
                    return urljoin(current, href)
        except Exception:
            pass
        return ""
