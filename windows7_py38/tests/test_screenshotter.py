from __future__ import annotations

from pathlib import Path

from scraper import KrishaScraper
from screenshotter import BrowserScreenshotter, _resolve_chromedriver_path


def test_screenshot_url_uses_shared_listing_params(tmp_path: Path) -> None:
    scraper = KrishaScraper(city="karaganda", owner_type=2, request_delay_sec=0)
    screenshotter = BrowserScreenshotter(output_root=tmp_path)

    url = screenshotter._build_page_url(scraper=scraper, category="prodazha", page_number=2)

    assert url == "https://krisha.kz/prodazha/kvartiry/karaganda/?das[_sys.fromAgent]=1&page=2"


def test_screenshotter_chromedriver_resolves_configured_path(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("KRISHA_CHROMEDRIVER", r"C:\drivers\chromedriver.exe")

    assert _resolve_chromedriver_path() == r"C:\drivers\chromedriver.exe"
