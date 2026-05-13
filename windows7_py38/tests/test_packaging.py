from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_linux_launcher_uses_single_standard_venv_name() -> None:
    run_script = (PROJECT_ROOT / "run.sh").read_text(encoding="utf-8")

    assert 'VENV=".venv"' in run_script
    assert 'python3 -m venv "$VENV"' in run_script
    assert ".venv-linux" not in run_script


def test_zip_script_does_not_package_wildcard_json_or_storage_state() -> None:
    zip_script = (PROJECT_ROOT / "make_zip.bat").read_text(encoding="utf-8")

    assert "'.\\*.json'" not in zip_script
    assert "'.\\config.json'" in zip_script
    assert "'.\\.krisha_storage_state.json'" not in zip_script
    assert "'.\\run.sh'" in zip_script
    assert "'.\\chromedriver.exe'" in zip_script
    assert "'.\\python-3.8.10-amd64.exe'" in zip_script
    assert "ChromeStandaloneSetup64.exe" in zip_script
    assert "Test-Path" in zip_script


def test_windows7_build_uses_selenium_instead_of_playwright() -> None:
    checked_files = [
        "requirements.txt",
        "messenger.py",
        "screenshotter.py",
        "start.bat",
        "1_INSTALL_ONCE.bat",
        "2_RUN_BOT.bat",
        "run.sh",
        "Dockerfile",
    ]
    combined = "\n".join((PROJECT_ROOT / path).read_text(encoding="utf-8") for path in checked_files)

    assert "selenium" in combined.lower()
    assert "playwright" not in combined.lower()


def test_windows7_launcher_requires_python38() -> None:
    start_script = (PROJECT_ROOT / "start.bat").read_text(encoding="utf-8")

    assert "sys.version_info[:2] == (3, 8)" in start_script
    assert "Python 3.8.10" in start_script


def test_client_batch_files_split_install_and_run() -> None:
    install_script = (PROJECT_ROOT / "1_INSTALL_ONCE.bat").read_text(encoding="utf-8")
    run_script = (PROJECT_ROOT / "2_RUN_BOT.bat").read_text(encoding="utf-8")
    preflight = (PROJECT_ROOT / "client_preflight.py").read_text(encoding="utf-8")

    assert "%BOOTSTRAP_PY% -m venv .venv" in install_script
    assert "BOOTSTRAP_PY" in install_script
    assert "py -3.8" in install_script
    assert "python-3.8.10-amd64.exe" in install_script
    assert "python-3.8.10.exe" in install_script
    assert "PROCESSOR_ARCHITECTURE" in install_script
    assert "PROCESSOR_ARCHITEW6432" in install_script
    assert "PYTHON_URL=https://www.python.org/ftp/python/3.8.10/" in install_script
    assert "%LOCALAPPDATA%\\Programs\\Python\\Python38\\python.exe" in install_script
    assert "%ProgramFiles%\\Python38\\python.exe" in install_script
    assert "%ProgramFiles(x86)%\\Python38-32\\python.exe" in install_script
    assert ".venv\\Scripts\\python.exe" in install_script
    assert "pip --disable-pip-version-check install -r requirements.txt" in install_script
    assert "PIP_DISABLE_PIP_VERSION_CHECK=1" in install_script
    assert "--disable-pip-version-check" in install_script
    assert "CHROMEDRIVER_VERSION=109.0.5414.74" in install_script
    assert "CHROMEDRIVER_URL=https://chromedriver.storage.googleapis.com/109.0.5414.74/chromedriver_win32.zip" in install_script
    assert "chromedriver_109_win32.zip" in install_script
    assert "certutil -urlcache" in install_script
    assert "ChromeStandaloneSetup64.exe" in install_script
    assert "GoogleChromeStandaloneEnterprise64.msi" in install_script
    assert "Chrome 109" in install_script
    assert "2_RUN_BOT.bat" in install_script
    assert "telegram_bot.py" not in install_script

    assert "telegram_bot.py" in run_script
    assert "pip install -r requirements.txt" not in run_script
    assert "1_INSTALL_ONCE.bat" in run_script
    assert "client_preflight.py" in run_script

    assert "KRISHA_CHROMEDRIVER" in preflight
    assert "KRISHA_CHROME_BINARY" in preflight
    assert "chromedriver.exe next to this file" in preflight
    assert "Chrome was not found" in preflight
    assert "Chrome 109" in preflight
    assert "PLACEHOLDERS" in preflight
    assert "version mismatch" in preflight
