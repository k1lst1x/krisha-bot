@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Krisha Bot Windows 7 Python 3.8

set "PYTHONIOENCODING=utf-8:backslashreplace"
set "PYTHONUTF8=1"

echo.
echo  =========================================
echo   Krisha Bot - Windows 7 / Python 3.8
echo  =========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python was not found.
    echo  Install Python 3.8.10, enable "Add Python to PATH", then run start.bat again.
    pause
    exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] This Windows 7 build must run on Python 3.8.x.
    python --version
    echo  Install Python 3.8.10 and make sure it is first in PATH.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Python %PY_VER% found.

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo.
        echo  [!] Created .env from .env.example.
        echo      Fill KRISHA_LOGIN, KRISHA_PASSWORD, TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_PHONES.
        echo.
        start notepad ".env"
        pause
        exit /b 0
    ) else (
        echo  [ERROR] .env.example was not found.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Could not create virtual environment.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\pip.exe" (
    echo  [ERROR] pip was not found in .venv.
    pause
    exit /b 1
)

if not exist ".venv\.deps_installed" (
    echo.
    echo  Installing dependencies...
    .venv\Scripts\python -m pip install --upgrade "pip<25" "setuptools<76" wheel
    if errorlevel 1 (
        echo  [ERROR] Could not upgrade pip tooling.
        pause
        exit /b 1
    )
    .venv\Scripts\pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo  [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
    echo. > .venv\.deps_installed
)

echo.
echo  Selenium uses an installed Chrome browser.
echo  On Windows 7 use Chrome 109 and a matching ChromeDriver 109.
echo  If chromedriver.exe is not in PATH, set KRISHA_CHROMEDRIVER in .env.
echo.

set PYTHONPATH=.
.venv\Scripts\python telegram_bot.py

echo.
echo  Bot stopped.
pause
