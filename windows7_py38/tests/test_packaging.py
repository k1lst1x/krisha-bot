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


def test_windows7_build_uses_selenium_instead_of_playwright() -> None:
    checked_files = [
        "requirements.txt",
        "messenger.py",
        "screenshotter.py",
        "start.bat",
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
