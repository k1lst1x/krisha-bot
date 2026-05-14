@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Krisha Bot - Run

set "PYTHONIOENCODING=utf-8:backslashreplace"
set "PYTHONUTF8=1"

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

.venv\Scripts\python client_preflight.py
if errorlevel 1 (
    echo.
    echo  Fix the issue above, save .env if it opened, then run this file again.
    echo  If Chrome is missing, install Chrome 109 for Windows 7.
    echo  If you have an offline Chrome 109 installer, put it next to 1_INSTALL_ONCE.bat and run install again.
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
