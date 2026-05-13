# KRISHA BOT Windows 7 / Python 3.8 - Plan

## Status: verified compatibility build

This folder is the Windows 7 / Python 3.8 variant. The root project remains the modern Python build.

## Completed

- [x] Copied the full project into `windows7_py38`.
- [x] Replaced Playwright with Selenium in `messenger.py` and `screenshotter.py`.
- [x] Pinned dependencies compatible with Python 3.8.
- [x] Added Windows 7 launch script requiring Python 3.8.x.
- [x] Added Chrome/ChromeDriver configuration via `.env`.
- [x] Added fallback to a temporary Chrome profile if the persistent profile fails to start.
- [x] Added fail-fast behavior when browser automation cannot start.
- [x] Added BOM-tolerant JSON config loading for Windows-edited files.
- [x] Verified Telegram token live via `getMe`.
- [x] Verified Selenium can open the krisha/kolesa auth page.
- [x] Verified krisha login flow live.
- [x] Verified one real test send through krisha.kz with Selenium.
- [x] Recorded the real test listing in `contacted.db` as `sent` to prevent duplicate outreach locally.
- [x] Verified normal test suite on Python 3.8.
- [x] Verified live-smoke tests on this machine.
- [x] Rebuilt `krisha-bot-windows7-py38.zip` without `.env`, `.venv`, DB, logs, screenshots, or Chrome profile.

## Remaining Client-Side Checklist

- [ ] Install Python 3.8.10 on the Windows 7 machine.
- [ ] Install Chrome 109 or another Chromium build that actually runs on Windows 7.
- [ ] Put the matching `chromedriver.exe` on the machine.
- [ ] Set `KRISHA_CHROMEDRIVER` in `.env` if `chromedriver.exe` is not in `PATH`.
- [ ] Run `start.bat`.
- [ ] Run `pytest` once after install if time allows.
- [ ] Run live-smoke tests before enabling production sending.
