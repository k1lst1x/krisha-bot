@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Krisha Bot - Install Once

echo.
echo  =========================================
echo   Krisha Bot - one-time install
echo  =========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python was not found.
    echo  Install Python 3.8.10 and enable "Add Python to PATH".
    echo  Then run this file again.
    echo.
    pause
    exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] This build requires Python 3.8.x.
    python --version
    echo  Install Python 3.8.10 and make sure it is first in PATH.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Python %PY_VER% found.

set CREATED_ENV=0
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        set CREATED_ENV=1
        echo  Created .env from .env.example.
    ) else (
        echo  [ERROR] .env.example was not found.
        echo.
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
        echo.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\pip.exe" (
    echo  [ERROR] pip was not found in .venv.
    echo.
    pause
    exit /b 1
)

echo.
echo  Installing/updating Python packages...
.venv\Scripts\python -m pip install --upgrade "pip<25" "setuptools<76" wheel
if errorlevel 1 (
    echo  [ERROR] Could not upgrade pip tooling.
    echo.
    pause
    exit /b 1
)

.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo  [ERROR] Dependency installation failed.
    echo.
    pause
    exit /b 1
)

echo. > .venv\.deps_installed

.venv\Scripts\python -c "import selenium, requests, bs4, dotenv; print(' Runtime imports OK')"
if errorlevel 1 (
    echo  [ERROR] Runtime import check failed.
    echo.
    pause
    exit /b 1
)

echo.
echo  Chrome note:
echo  - On Windows 7 use Chrome 109.
echo  - Use matching ChromeDriver 109.
echo  - If chromedriver.exe is not in PATH, set KRISHA_CHROMEDRIVER in .env.
echo.

if "%CREATED_ENV%"=="1" (
    echo  .env was created. Fill it now, save, then run 2_RUN_BOT.bat.
    echo.
    start notepad ".env"
) else (
    echo  .env already exists. Check it if credentials changed.
)

echo.
echo  Install finished.
echo  Next time use: 2_RUN_BOT.bat
echo.
pause
