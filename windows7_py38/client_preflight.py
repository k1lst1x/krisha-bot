from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Optional, Sequence

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
REQUIRED_ENV = [
    "KRISHA_LOGIN",
    "KRISHA_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_PHONES",
]
PLACEHOLDERS = ("123456", "+7700", "your_", "your-", "token", "password")


def missing_required_env(env: Mapping[str, str]) -> list[str]:
    missing: list[str] = []
    for key in REQUIRED_ENV:
        value = env.get(key, "").strip()
        lower_value = value.lower()
        if not value or any(lower_value.startswith(item) for item in PLACEHOLDERS) or "..." in value:
            missing.append(key)
    return missing


def _existing_path(path_value: str, project_root: Path) -> Optional[Path]:
    if not path_value:
        return None
    candidate = Path(path_value.strip().strip('"'))
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate if candidate.exists() else None


def resolve_chromedriver(env: Mapping[str, str], project_root: Path = PROJECT_ROOT) -> Optional[Path]:
    configured = _existing_path(env.get("KRISHA_CHROMEDRIVER", ""), project_root)
    if configured:
        return configured

    local_driver = project_root / "chromedriver.exe"
    if local_driver.exists():
        return local_driver

    found = shutil.which("chromedriver")
    return Path(found) if found else None


def resolve_chrome(env: Mapping[str, str]) -> Optional[Path]:
    configured = env.get("KRISHA_CHROME_BINARY", "").strip().strip('"')
    candidates: Sequence[str] = [
        configured,
        os.path.join(env.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(env.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(env.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for item in candidates:
        if item and Path(item).exists():
            return Path(item)
    return None


def _hiword(value: int) -> int:
    return (value >> 16) & 0xFFFF


def _loword(value: int) -> int:
    return value & 0xFFFF


def get_windows_file_version(path: Path) -> str:
    if os.name != "nt" or not path.exists():
        return ""

    class VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", ctypes.c_uint32),
            ("dwStrucVersion", ctypes.c_uint32),
            ("dwFileVersionMS", ctypes.c_uint32),
            ("dwFileVersionLS", ctypes.c_uint32),
            ("dwProductVersionMS", ctypes.c_uint32),
            ("dwProductVersionLS", ctypes.c_uint32),
            ("dwFileFlagsMask", ctypes.c_uint32),
            ("dwFileFlags", ctypes.c_uint32),
            ("dwFileOS", ctypes.c_uint32),
            ("dwFileType", ctypes.c_uint32),
            ("dwFileSubtype", ctypes.c_uint32),
            ("dwFileDateMS", ctypes.c_uint32),
            ("dwFileDateLS", ctypes.c_uint32),
        ]

    size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return ""

    buffer = ctypes.create_string_buffer(size)
    if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer):
        return ""

    value = ctypes.c_void_p()
    value_len = ctypes.c_uint()
    if not ctypes.windll.version.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(value_len)):
        return ""

    info = ctypes.cast(value, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    if info.dwSignature != 0xFEEF04BD:
        return ""

    return ".".join(
        str(part)
        for part in (
            _hiword(info.dwFileVersionMS),
            _loword(info.dwFileVersionMS),
            _hiword(info.dwFileVersionLS),
            _loword(info.dwFileVersionLS),
        )
    )


def get_chromedriver_version(path: Path) -> str:
    try:
        output = subprocess.check_output(
            [str(path), "--version"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return output.strip()


def major_version(version_text: str) -> Optional[int]:
    match = re.search(r"\b(\d+)\.", version_text)
    return int(match.group(1)) if match else None


def run_preflight(env: Mapping[str, str], project_root: Path = PROJECT_ROOT) -> int:
    missing = missing_required_env(env)
    if missing:
        print("Missing .env values: " + ", ".join(missing))
        return 1
    print("Environment OK")

    driver = resolve_chromedriver(env, project_root)
    if not driver:
        print("ChromeDriver was not found. Put chromedriver.exe next to this file or set KRISHA_CHROMEDRIVER in .env")
        return 1
    print(f"ChromeDriver OK: {driver}")

    chrome = resolve_chrome(env)
    if not chrome:
        print("Chrome was not found. Install Chrome 109 for Windows 7 or set KRISHA_CHROME_BINARY in .env")
        return 1
    print(f"Chrome OK: {chrome}")

    driver_version = get_chromedriver_version(driver)
    chrome_version = get_windows_file_version(chrome)
    driver_major = major_version(driver_version)
    chrome_major = major_version(chrome_version)
    if driver_major and chrome_major and driver_major != chrome_major:
        print(
            "Chrome/ChromeDriver version mismatch: "
            f"Chrome {chrome_version}, ChromeDriver {driver_version}. "
            "Use matching ChromeDriver, or use Chrome 109 with ChromeDriver 109 on Windows 7."
        )
        return 1

    if chrome_major and chrome_major != 109:
        print(f"WARNING: Chrome major version is {chrome_major}; Windows 7 should use Chrome 109.")
    return 0


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return run_preflight(os.environ, PROJECT_ROOT)


if __name__ == "__main__":
    sys.exit(main())
