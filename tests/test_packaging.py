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
