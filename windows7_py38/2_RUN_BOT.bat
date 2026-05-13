@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Krisha Bot - Run

echo.
echo  =========================================
echo   Krisha Bot - run
echo  =========================================
echo.

if not exist ".env" (
    echo  [ERROR] .env was not found.
    echo  Run 1_INSTALL_ONCE.bat first.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo  [ERROR] Virtual environment was not found.
    echo  Run 1_INSTALL_ONCE.bat first.
    echo.
    pause
    exit /b 1
)

.venv\Scripts\python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] .venv is not Python 3.8.x.
    .venv\Scripts\python --version
    echo  Delete .venv and run 1_INSTALL_ONCE.bat again with Python 3.8.10.
    echo.
    pause
    exit /b 1
)

.venv\Scripts\python -c "from dotenv import load_dotenv; import os, sys; load_dotenv('.env'); required=['KRISHA_LOGIN','KRISHA_PASSWORD','TELEGRAM_BOT_TOKEN','TELEGRAM_ALLOWED_PHONES']; placeholders=('123456','+7700','your_','your-','token','password'); missing=[k for k in required if (not os.getenv(k,'').strip()) or any(os.getenv(k,'').strip().lower().startswith(p) for p in placeholders) or '...' in os.getenv(k,'')]; print('Missing .env values: '+', '.join(missing)) if missing else print('Environment OK'); sys.exit(1 if missing else 0)"
if errorlevel 1 (
    echo.
    echo  Fill .env, save it, then run this file again.
    echo.
    start notepad ".env"
    pause
    exit /b 1
)

.venv\Scripts\python -c "from dotenv import load_dotenv; from pathlib import Path; import os, shutil, sys; load_dotenv('.env'); driver=os.getenv('KRISHA_CHROMEDRIVER','').strip().strip('\"'); ok=(Path(driver).exists() if driver else (Path('chromedriver.exe').exists() or shutil.which('chromedriver'))); print('ChromeDriver OK' if ok else 'ChromeDriver was not found. Put chromedriver.exe next to this file or set KRISHA_CHROMEDRIVER in .env'); sys.exit(0 if ok else 1)"
if errorlevel 1 (
    echo.
    echo  Fix KRISHA_CHROMEDRIVER in .env or put chromedriver.exe in PATH.
    echo.
    start notepad ".env"
    pause
    exit /b 1
)

echo.
echo  Starting bot...
echo  Close this window or press Ctrl+C to stop.
echo.

set PYTHONPATH=.
.venv\Scripts\python telegram_bot.py

echo.
echo  Bot stopped.
pause
