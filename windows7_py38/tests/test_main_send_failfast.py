from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import main
from messenger import MessageResult
from scraper import Listing


def test_run_stops_after_global_browser_start_failure(tmp_path: Path, monkeypatch) -> None:
    listings = [
        Listing(
            listing_id="first",
            title="First",
            price="1",
            district="A",
            url="https://krisha.kz/a/show/first",
            category="prodazha",
        ),
        Listing(
            listing_id="second",
            title="Second",
            price="2",
            district="B",
            url="https://krisha.kz/a/show/second",
            category="prodazha",
        ),
    ]
    attempted_listing_ids = []

    class FakeScraper:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN001
            pass

        @staticmethod
        def extra_params_from_config(config):  # noqa: ANN001
            return {}

        def iter_listings(self, *args, **kwargs):  # noqa: ANN001
            return iter(listings)

    class FakeMessenger:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN001
            pass

        def send_message(self, listing, message: str, dry_run: bool = True):  # noqa: ANN001
            attempted_listing_ids.append(listing.listing_id)
            return MessageResult(
                listing_id=listing.listing_id,
                status="failed",
                response="Chrome/ChromeDriver could not start. Original error: boom",
            )

    config = {
        "city": "karaganda",
        "categories": ["prodazha"],
        "goal": "Здравствуйте",
        "max_pages": 1,
        "page_stop_below": 0,
        "request_delay_sec": 0,
    }

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "parse_args", lambda: Namespace(
        config="config.json",
        dry_run=False,
        send=True,
        limit=2,
        screenshots=False,
        auth_screenshot=False,
        show_browser=False,
        no_telegram_sync=True,
        telegram_sync_only=False,
    ))
    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(main, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "load_config", lambda path: config)
    monkeypatch.setattr(main, "sync_config_from_telegram", lambda **kwargs: 0)
    monkeypatch.setattr(main, "KrishaScraper", FakeScraper)
    monkeypatch.setattr(main, "KrishaMessenger", FakeMessenger)

    exit_code = main.run()

    assert exit_code == 1
    assert attempted_listing_ids == ["first"]
