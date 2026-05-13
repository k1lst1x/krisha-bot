from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_runtime_env() -> Path:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        pytest.skip(".env is not present; live smoke checks are local-only")
    load_dotenv(env_path, override=False)
    return env_path


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on", "y"}


def test_local_env_has_required_runtime_values() -> None:
    _load_runtime_env()

    required = [
        "KRISHA_LOGIN",
        "KRISHA_PASSWORD",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_PHONES",
        "TELEGRAM_RUN_TIMEOUT_SEC",
    ]
    missing = [key for key in required if not os.getenv(key, "").strip()]

    assert missing == []


def test_telegram_token_get_me_live() -> None:
    _load_runtime_env()
    if not _enabled("RUN_LIVE_SMOKE_TESTS"):
        pytest.skip("set RUN_LIVE_SMOKE_TESTS=1 to call Telegram API")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        pytest.skip("TELEGRAM_BOT_TOKEN is empty")

    response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)

    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert data.get("result", {}).get("id")


def test_selenium_can_open_krisha_auth_page_live(tmp_path: Path) -> None:
    _load_runtime_env()
    if not _enabled("RUN_BROWSER_SMOKE_TESTS"):
        pytest.skip("set RUN_BROWSER_SMOKE_TESTS=1 to start Selenium/Chrome")

    from messenger import KrishaMessenger, LOGIN_URL

    os.environ["KRISHA_CHROME_PROFILE_DIR"] = str(tmp_path / "chrome-profile")
    messenger = KrishaMessenger(headless=True, timeout_ms=45_000, settle_ms=1_000)
    try:
        page = messenger._driver_page()
        page.get(LOGIN_URL)

        current_url = page.current_url.lower()
        assert "kolesa.kz" in current_url or "krisha.kz" in current_url
        assert messenger._is_login_page(page) or not page.find_elements("css selector", "input[name='login']")
    finally:
        messenger.close()


def test_krisha_login_flow_live(tmp_path: Path) -> None:
    _load_runtime_env()
    if not _enabled("RUN_KRISHA_LOGIN_SMOKE_TESTS"):
        pytest.skip("set RUN_KRISHA_LOGIN_SMOKE_TESTS=1 to attempt real Krisha login")

    from messenger import KrishaMessenger, LOGIN_URL

    os.environ["KRISHA_CHROME_PROFILE_DIR"] = str(tmp_path / "chrome-profile")
    messenger = KrishaMessenger(
        login=os.getenv("KRISHA_LOGIN", ""),
        password=os.getenv("KRISHA_PASSWORD", ""),
        headless=True,
        timeout_ms=45_000,
        settle_ms=1_000,
    )
    try:
        page = messenger._driver_page()
        page.get(LOGIN_URL)
        login_error = messenger._perform_login(page)

        assert login_error is None
        assert not messenger._is_login_page(page)
    finally:
        messenger.close()
