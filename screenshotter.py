from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

from scraper import KrishaScraper


LOGGER = logging.getLogger(__name__)


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

        with sync_playwright() as playwright:
            LOGGER.info("Launching Chromium for screenshots headless=%s", self.headless)
            browser = playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-gpu", "--no-sandbox"],
            )
            LOGGER.info("Creating browser context")
            context = browser.new_context(
                viewport={"width": self.viewport_width, "height": self.viewport_height},
                locale="ru-RU",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
            )
            LOGGER.info("Creating browser page")
            page = context.new_page()

            try:
                for category in categories:
                    for page_number in range(1, pages + 1):
                        url = self._build_page_url(scraper, category, page_number)
                        screenshot_path = run_dir / f"{category}-page-{page_number}.png"
                        LOGGER.info("Opening browser page for screenshot: %s", url)
                        page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                        page.wait_for_timeout(self.settle_ms)
                        page.screenshot(path=screenshot_path, full_page=True)
                        saved_paths.append(screenshot_path)
                        LOGGER.info("Saved screenshot: %s", screenshot_path)
            finally:
                context.close()
                browser.close()

        return saved_paths

    def capture_auth_page(self, url: str) -> Path:
        run_dir = self.output_root / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = run_dir / "auth-login-page.png"

        with sync_playwright() as playwright:
            LOGGER.info("Launching Chromium for auth screenshot headless=%s", self.headless)
            browser = playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-gpu", "--no-sandbox"],
            )
            LOGGER.info("Creating browser context")
            context = browser.new_context(
                viewport={"width": self.viewport_width, "height": self.viewport_height},
                locale="ru-RU",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
            )
            LOGGER.info("Creating browser page")
            page = context.new_page()

            try:
                LOGGER.info("Opening auth page for screenshot: %s", url)
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                page.wait_for_timeout(self.settle_ms)
                page.screenshot(path=screenshot_path, full_page=True)
                LOGGER.info("Saved auth screenshot: %s", screenshot_path)
            finally:
                context.close()
                browser.close()

        return screenshot_path

    def _build_page_url(self, scraper: KrishaScraper, category: str, page_number: int) -> str:
        params = scraper._listing_page_params(page=page_number)

        url = scraper.build_category_url(category)
        if not params:
            return url
        return f"{url}?{urlencode(params, safe='[]')}"
