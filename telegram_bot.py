from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from telegram_control import sync_config_from_telegram


PROJECT_ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("telegram-bot")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram control bot for krisha-bot")
    parser.add_argument("--config", default="config.json", help="Path to config JSON")
    parser.add_argument("--once", action="store_true", help="Handle updates once and exit")
    parser.add_argument(
        "--idle-sleep-sec",
        type=float,
        default=0.5,
        help="Sleep time between iterations when long polling timeout is 0",
    )
    return parser.parse_args()


def setup_logging() -> None:
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / "telegram-bot.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def run() -> int:
    args = parse_args()
    setup_logging()
    load_dotenv(PROJECT_ROOT / ".env", override=True)

    if not os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
        LOGGER.error("TELEGRAM_BOT_TOKEN is empty. Fill it in .env")
        return 2

    current_poll_timeout = os.getenv("TELEGRAM_POLL_TIMEOUT_SEC", "").strip()
    if not current_poll_timeout or current_poll_timeout == "0":
        os.environ["TELEGRAM_POLL_TIMEOUT_SEC"] = "20"
        LOGGER.info("TELEGRAM_POLL_TIMEOUT_SEC was empty/0, using 20 seconds for long polling")

    config_path = (PROJECT_ROOT / args.config).resolve()
    LOGGER.info("Telegram bot service started")

    try:
        while True:
            try:
                load_dotenv(PROJECT_ROOT / ".env", override=True)
                processed = sync_config_from_telegram(
                    config_path=config_path,
                    project_root=PROJECT_ROOT,
                    allow_run_command=True,
                )
                if processed:
                    LOGGER.info("Processed Telegram updates: %s", processed)
            except Exception:
                LOGGER.exception("Unhandled error in Telegram polling iteration")
                if args.once:
                    return 1
                time.sleep(1.0)
                continue

            if args.once:
                break
            if os.getenv("TELEGRAM_POLL_TIMEOUT_SEC", "0").strip() == "0":
                time.sleep(max(0.1, args.idle_sleep_sec))
    except KeyboardInterrupt:
        LOGGER.info("Telegram bot service stopped by user")
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
