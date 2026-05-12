@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Krisha Bot

echo.
echo  =========================================
echo   Krisha Bot — запуск
echo  =========================================
echo.

:: ── 1. Проверить Python ───────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ОШИБКА] Python не найден.
    echo.
    echo  Установи Python 3.11+ с сайта https://python.org
    echo  При установке поставь галочку "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Python %PY_VER% найден.

:: ── 2. Проверить .env ─────────────────────────────────────────────────
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo.
        echo  [!] Файл .env создан из шаблона.
        echo      Открой .env в блокноте и заполни:
        echo.
        echo        KRISHA_LOGIN    — телефон от krisha.kz
        echo        KRISHA_PASSWORD — пароль от krisha.kz
        echo        TELEGRAM_BOT_TOKEN — токен от @BotFather
        echo        TELEGRAM_ALLOWED_PHONES — твой номер телефона
        echo.
        echo  После заполнения запусти start.bat снова.
        echo.
        start notepad ".env"
        pause
        exit /b 0
    ) else (
        echo  [ОШИБКА] Файл .env не найден и нет шаблона .env.example
        pause
        exit /b 1
    )
)

:: Проверить что токен заполнен
python -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
token = os.getenv('TELEGRAM_BOT_TOKEN','').strip()
if not token or token.startswith('123456789'):
    print('NOT_SET')
else:
    print('OK')
" 2>nul > .token_check.tmp
set /p TOKEN_STATUS=<.token_check.tmp
del .token_check.tmp 2>nul

if "%TOKEN_STATUS%"=="NOT_SET" (
    echo  [!] TELEGRAM_BOT_TOKEN не заполнен в .env
    echo      Открой .env и вставь токен от @BotFather
    echo.
    start notepad ".env"
    pause
    exit /b 0
)

:: ── 3. Создать виртуальное окружение если нет ─────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  Создаю виртуальное окружение...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ОШИБКА] Не удалось создать виртуальное окружение.
        pause
        exit /b 1
    )
    echo  Готово.
)

:: ── 4. Установить зависимости если нужно ─────────────────────────────
if not exist ".venv\Scripts\pip.exe" (
    echo  [ОШИБКА] pip не найден в .venv
    pause
    exit /b 1
)

:: Флаг — зависимости уже установлены
if not exist ".venv\.deps_installed" (
    echo.
    echo  Устанавливаю зависимости (первый раз, займёт 1-3 мин)...
    .venv\Scripts\pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo  [ОШИБКА] Установка зависимостей не удалась.
        pause
        exit /b 1
    )
    echo  Зависимости установлены.

    echo.
    echo  Устанавливаю браузер Chromium для Playwright...
    .venv\Scripts\python -m playwright install chromium
    if errorlevel 1 (
        echo  [ОШИБКА] Установка Playwright не удалась.
        pause
        exit /b 1
    )
    echo  Chromium установлен.

    echo. > .venv\.deps_installed
)

:: ── 5. Запустить бота ─────────────────────────────────────────────────
echo.
echo  Запускаю бота...
echo  (чтобы остановить — закрой это окно или нажми Ctrl+C)
echo.

set PYTHONPATH=.
.venv\Scripts\python telegram_bot.py

echo.
echo  Бот остановлен.
pause
