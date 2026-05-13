from __future__ import annotations

from pathlib import Path

import client_preflight


def _valid_env(tmp_path: Path) -> dict[str, str]:
    chrome = tmp_path / "chrome.exe"
    driver = tmp_path / "chromedriver.exe"
    chrome.write_text("", encoding="utf-8")
    driver.write_text("", encoding="utf-8")
    return {
        "KRISHA_LOGIN": "+77770000000",
        "KRISHA_PASSWORD": "real-value",
        "TELEGRAM_BOT_TOKEN": "987654321:bot-secret",
        "TELEGRAM_ALLOWED_PHONES": "+77770000000",
        "KRISHA_CHROME_BINARY": str(chrome),
        "KRISHA_CHROMEDRIVER": str(driver),
        "ProgramFiles": str(tmp_path / "Program Files"),
        "ProgramFiles(x86)": str(tmp_path / "Program Files (x86)"),
        "LOCALAPPDATA": str(tmp_path / "LocalAppData"),
    }


def test_missing_required_env_rejects_empty_and_placeholders() -> None:
    missing = client_preflight.missing_required_env(
        {
            "KRISHA_LOGIN": "+7700...",
            "KRISHA_PASSWORD": "your_password",
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_ALLOWED_PHONES": "+77770000000",
        }
    )

    assert missing == ["KRISHA_LOGIN", "KRISHA_PASSWORD", "TELEGRAM_BOT_TOKEN"]


def test_preflight_passes_with_matching_browser_versions(monkeypatch, tmp_path: Path) -> None:
    env = _valid_env(tmp_path)
    monkeypatch.setattr(client_preflight, "get_windows_file_version", lambda path: "109.0.5414.120")
    monkeypatch.setattr(client_preflight, "get_chromedriver_version", lambda path: "ChromeDriver 109.0.5414.74")

    assert client_preflight.run_preflight(env, tmp_path) == 0


def test_preflight_rejects_chrome_chromedriver_major_mismatch(monkeypatch, tmp_path: Path) -> None:
    env = _valid_env(tmp_path)
    monkeypatch.setattr(client_preflight, "get_windows_file_version", lambda path: "136.0.7103.93")
    monkeypatch.setattr(client_preflight, "get_chromedriver_version", lambda path: "ChromeDriver 109.0.5414.74")

    assert client_preflight.run_preflight(env, tmp_path) == 1


def test_preflight_rejects_missing_chrome(tmp_path: Path) -> None:
    env = _valid_env(tmp_path)
    Path(env["KRISHA_CHROME_BINARY"]).unlink()

    assert client_preflight.run_preflight(env, tmp_path) == 1
