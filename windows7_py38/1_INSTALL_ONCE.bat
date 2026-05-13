@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Krisha Bot - Install Once
set PIP_DISABLE_PIP_VERSION_CHECK=1

echo.
echo  =========================================
echo   Krisha Bot - one-time install
echo  =========================================
echo.

set "BOOTSTRAP_PY="

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo  [ERROR] Existing .venv is not Python 3.8.x.
        .venv\Scripts\python.exe --version
        echo  Delete .venv, install Python 3.8.10, then run this file again.
        echo.
        pause
        exit /b 1
    )
    set "BOOTSTRAP_PY=.venv\Scripts\python.exe"
)

if not defined BOOTSTRAP_PY (
    python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 set "BOOTSTRAP_PY=python"
)

if not defined BOOTSTRAP_PY (
    py -3.8 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 set "BOOTSTRAP_PY=py -3.8"
)

if not defined BOOTSTRAP_PY (
    echo  [ERROR] Python 3.8.x was not found.
    echo  Install Python 3.8.10 and enable "Add Python to PATH".
    echo  If multiple Python versions are installed, make sure py -3.8 works.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('%BOOTSTRAP_PY% --version 2^>^&1') do set PY_VER=%%v
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
    %BOOTSTRAP_PY% -m venv .venv
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
.venv\Scripts\python -m pip --disable-pip-version-check install --upgrade "pip<25" "setuptools<76" wheel
if errorlevel 1 (
    echo  [ERROR] Could not upgrade pip tooling.
    echo.
    pause
    exit /b 1
)

.venv\Scripts\pip --disable-pip-version-check install -r requirements.txt
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
echo  - Put chromedriver.exe next to these files, or set KRISHA_CHROMEDRIVER in .env.
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
