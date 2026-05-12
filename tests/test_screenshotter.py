from pathlib import Path

from scraper import KrishaScraper
from screenshotter import BrowserScreenshotter


def test_screenshot_url_uses_shared_listing_params(tmp_path: Path) -> None:
    scraper = KrishaScraper(city="karaganda", owner_type=2, request_delay_sec=0)
    screenshotter = BrowserScreenshotter(output_root=tmp_path)

    url = screenshotter._build_page_url(scraper=scraper, category="prodazha", page_number=2)

    assert url == "https://krisha.kz/prodazha/kvartiry/karaganda/?das[_sys.fromAgent]=1&page=2"
