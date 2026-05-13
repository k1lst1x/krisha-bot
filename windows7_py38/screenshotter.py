from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from scraper import KrishaScraper


LOGGER = logging.getLogger(__name__)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/109.0.0.0 Safari/537.36"
)


class BrowserScreenshotter:
    def __init__(
        self,
        output_root: Path,
        headless: bool = True,
        viewport_width: int = 1365,
        viewport_height: int = 900,
        timeout_ms: int = 45_000,
        settle_ms: int = 2_500,
    ) -> None:
        self.output_root = output_root
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.timeout_ms = timeout_ms
        self.timeout_sec = timeout_ms / 1000
        self.settle_ms = settle_ms

    def capture_category_pages(
        self,
        scraper: KrishaScraper,
        categories: list[str],
        pages: int = 1,
    ) -> list[Path]:
        run_dir = self.output_root / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        saved_paths: list[Path] = []

        browser = self._create_driver()
        try:
            for category in categories:
                for page_number in range(1, pages + 1):
                    url = self._build_page_url(scraper, category, page_number)
                    screenshot_path = run_dir / f"{category}-page-{page_number}.png"
                    LOGGER.info("Opening browser page for screenshot: %s", url)
                    browser.get(url)
                    self._wait_ms(self.settle_ms)
                    browser.save_screenshot(str(screenshot_path))
                    saved_paths.append(screenshot_path)
                    LOGGER.info("Saved screenshot: %s", screenshot_path)
        finally:
            browser.quit()

        return saved_paths

    def capture_auth_page(self, url: str) -> Path:
        run_dir = self.output_root / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = run_dir / "auth-login-page.png"

        browser = self._create_driver()
        try:
            LOGGER.info("Opening auth page for screenshot: %s", url)
            browser.get(url)
            self._wait_ms(self.settle_ms)
            browser.save_screenshot(str(screenshot_path))
            LOGGER.info("Saved auth screenshot: %s", screenshot_path)
        finally:
            browser.quit()

        return screenshot_path

    def _build_page_url(self, scraper: KrishaScraper, category: str, page_number: int) -> str:
        params = scraper._listing_page_params(page=page_number)

        url = scraper.build_category_url(category)
        if not params:
            return url
        return f"{url}?{urlencode(params, safe='[]')}"

    def _create_driver(self):
        options = Options()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=ru-RU")
        options.add_argument(f"--window-size={self.viewport_width},{self.viewport_height}")
        options.add_argument(f"--user-agent={DEFAULT_USER_AGENT}")
        if self.headless:
            options.add_argument("--headless")

        chrome_binary = os.getenv("KRISHA_CHROME_BINARY", "").strip()
        if chrome_binary:
            options.binary_location = chrome_binary

        driver_path = os.getenv("KRISHA_CHROMEDRIVER", "").strip()
        service = Service(executable_path=driver_path) if driver_path else Service()
        try:
            browser = webdriver.Chrome(service=service, options=options)
        except WebDriverException as exc:
            hint = (
                "Chrome/ChromeDriver could not start. On Windows 7 use Chrome 109 "
                "and set KRISHA_CHROMEDRIVER to the matching chromedriver.exe path "
                "if Selenium Manager cannot download it automatically."
            )
            raise RuntimeError(f"{hint} Original error: {exc}") from exc

        browser.set_page_load_timeout(self.timeout_sec)
        return browser

    @staticmethod
    def _wait_ms(ms: int) -> None:
        if ms > 0:
            time.sleep(ms / 1000)
