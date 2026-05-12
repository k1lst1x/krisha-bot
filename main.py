from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from listing_filters import ListingFilters
from messenger import KrishaMessenger
from scraper import KrishaScraper, Listing
from telegram_control import sync_config_from_telegram


PROJECT_ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("krisha-bot")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Krisha dry-run outreach pipeline")
    parser.add_argument("--config", default="config.json", help="Path to config JSON")
    parser.add_argument("--dry-run", action="store_true", help="Do not send messages")
    parser.add_argument("--send", action="store_true", help="Attempt real sending")
    parser.add_argument("--limit", type=int, default=None, help="Override max messages per run")
    parser.add_argument("--screenshots", action="store_true", help="Save browser screenshots")
    parser.add_argument("--auth-screenshot", action="store_true", help="Save login page screenshot")
    parser.add_argument("--show-browser", action="store_true", help="Run screenshot browser visibly")
    parser.add_argument(
        "--no-telegram-sync",
        action="store_true",
        help="Skip config updates from Telegram commands",
    )
    parser.add_argument(
        "--telegram-sync-only",
        action="store_true",
        help="Apply Telegram commands to config and exit",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def setup_logging() -> None:
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / "activity.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            listing_id TEXT PRIMARY KEY,
            sent_at TEXT NOT NULL,
            message TEXT NOT NULL,
            response TEXT,
            status TEXT NOT NULL,
            listing_url TEXT
        )
        """
    )
    conn.commit()
    return conn


def was_contacted(conn: sqlite3.Connection, listing_id: str, include_dry_run: bool = True) -> bool:
    # Do not block retries after transient `failed` statuses.
    # Block only for terminal outcomes:
    # - sent
    # - dry_run (when include_dry_run=True)
    # - skipped_no_chat (listing has no message button)
    if include_dry_run:
        row = conn.execute(
            """
            SELECT 1
            FROM contacts
            WHERE listing_id = ?
              AND status IN ('sent', 'dry_run', 'skipped_no_chat')
            LIMIT 1
            """,
            (listing_id,),
        ).fetchone()
        return row is not None

    row = conn.execute(
        """
        SELECT 1
        FROM contacts
        WHERE listing_id = ?
          AND status IN ('sent', 'skipped_no_chat')
        LIMIT 1
        """,
        (listing_id,),
    ).fetchone()
    return row is not None


def record_contact(
    conn: sqlite3.Connection,
    listing: Listing,
    message: str,
    status: str,
    response: str = "",
) -> None:
    # Never overwrite a terminal status (sent / skipped_no_chat) — this prevents
    # a failed retry from erasing a successful send and causing a duplicate message.
    conn.execute(
        """
        INSERT INTO contacts
            (listing_id, sent_at, message, response, status, listing_url)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(listing_id) DO UPDATE SET
            sent_at     = excluded.sent_at,
            message     = excluded.message,
            response    = excluded.response,
            status      = excluded.status,
            listing_url = excluded.listing_url
        WHERE contacts.status NOT IN ('sent', 'skipped_no_chat')
        """,
        (
            listing.listing_id,
            datetime.now(timezone.utc).isoformat(),
            message,
            response,
            status,
            listing.url,
        ),
    )
    conn.commit()


def run() -> int:
    args = parse_args()
    setup_logging()
    load_dotenv(PROJECT_ROOT / ".env", override=True)

    config_path = (PROJECT_ROOT / args.config).resolve()
    if not args.no_telegram_sync:
        command_count = sync_config_from_telegram(config_path=config_path, project_root=PROJECT_ROOT)
        if command_count:
            LOGGER.info("Applied %s Telegram command(s) to config", command_count)
    if args.telegram_sync_only:
        LOGGER.info("Telegram sync-only mode completed")
        return 0

    config = load_config(config_path)
    dry_run = args.dry_run or not args.send
    max_messages = (
        args.limit if args.limit is not None else int(config.get("max_messages_per_run", 20))
    )
    listing_filters = ListingFilters.from_config(config)

    LOGGER.info("Starting run dry_run=%s max_messages=%s", dry_run, max_messages)
    LOGGER.info(
        "Active listing filters min_price=%s max_price=%s rooms=%s location_keywords=%s",
        listing_filters.min_price_tenge,
        listing_filters.max_price_tenge,
        sorted(listing_filters.rooms) if listing_filters.rooms else None,
        listing_filters.location_keywords,
    )

    scraper = KrishaScraper(
        city=config["city"],
        owner_type=config.get("owner_type"),
        request_delay_sec=float(config.get("request_delay_sec", 1.5)),
        extra_params=KrishaScraper.extra_params_from_config(config),
    )

    if args.screenshots:
        from screenshotter import BrowserScreenshotter

        screenshotter = BrowserScreenshotter(
            output_root=PROJECT_ROOT / "screenshots",
            headless=not args.show_browser,
            viewport_width=int(config.get("screenshot_viewport_width", 1365)),
            viewport_height=int(config.get("screenshot_viewport_height", 900)),
        )
        saved_paths = screenshotter.capture_category_pages(
            scraper=scraper,
            categories=list(config.get("categories", ["arenda"])),
            pages=int(config.get("screenshot_pages", 1)),
        )
        LOGGER.info("Saved %s browser screenshots", len(saved_paths))

    if args.auth_screenshot:
        from screenshotter import BrowserScreenshotter

        screenshotter = BrowserScreenshotter(
            output_root=PROJECT_ROOT / "screenshots",
            headless=not args.show_browser,
            viewport_width=int(config.get("screenshot_viewport_width", 1365)),
            viewport_height=int(config.get("screenshot_viewport_height", 900)),
        )
        saved_path = screenshotter.capture_auth_page("https://krisha.kz/my")
        LOGGER.info("Saved auth screenshot: %s", saved_path)

    if max_messages <= 0:
        LOGGER.info("Skipping listing processing because max_messages=%s", max_messages)
        return 0

    message = str(config.get("goal") or "").strip()
    if not message:
        LOGGER.error("'goal' is empty in config — set a message text to send")
        return 1

    messenger = KrishaMessenger(
        login=(
            os.getenv("KRISHA_LOGIN", "")
            or os.getenv("KRISHA_PHONE", "")
            or os.getenv("KRISHA_EMAIL", "")
        ),
        password=os.getenv("KRISHA_PASSWORD", ""),
    )

    conn = init_db(PROJECT_ROOT / "contacted.db")
    delivered = 0
    attempted = 0

    try:
        for category in config.get("categories", ["arenda"]):
            listings = scraper.iter_listings(
                category=category,
                max_pages=int(config.get("max_pages", 1)),
                page_stop_below=int(config.get("page_stop_below", 20)),
                fetch_details=bool(config.get("fetch_details", False)),
            )

            for listing in listings:
                if delivered >= max_messages:
                    LOGGER.info("Reached target delivered=%s", max_messages)
                    return 0

                accepted, reason = listing_filters.accepts(listing)
                if not accepted:
                    LOGGER.info(
                        "Skipping listing_id=%s filter_reason=%s url=%s",
                        listing.listing_id,
                        reason,
                        listing.url,
                    )
                    continue

                if was_contacted(conn, listing.listing_id, include_dry_run=dry_run):
                    LOGGER.info("Skipping already contacted listing_id=%s", listing.listing_id)
                    continue

                result = messenger.send_message(listing, message, dry_run=dry_run)
                LOGGER.info(
                    "Processed listing_id=%s status=%s url=%s message=%s",
                    listing.listing_id,
                    result.status,
                    listing.url,
                    message,
                )
                LOGGER.info(
                    "RESULT %s",
                    json.dumps(
                        {
                            "listing_id": listing.listing_id,
                            "status": result.status,
                            "district": listing.district or "",
                            "price": listing.price or "",
                            "url": listing.url,
                            "chat_url": result.chat_url,
                            "response": result.response,
                            "message": message,
                        },
                        ensure_ascii=False,
                    ),
                )

                record_contact(
                    conn=conn,
                    listing=listing,
                    message=message,
                    status=result.status,
                    response=result.response,
                )
                attempted += 1
                status = (result.status or "").strip().lower()
                if status in {"sent", "dry_run"}:
                    delivered += 1
                if delivered < max_messages and not dry_run and status in {"sent"}:
                    time.sleep(float(config.get("delay_between_messages_sec", 45)))
    finally:
        conn.close()

    LOGGER.info("Finished run delivered=%s attempted=%s", delivered, attempted)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        LOGGER.warning("Stopped by user")
        raise SystemExit(130)
