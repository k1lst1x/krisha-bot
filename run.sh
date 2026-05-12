#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo ""
echo " ========================================="
echo "  Krisha Bot — запуск"
echo " ========================================="
echo ""

# ── 1. Проверить Python ───────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo " [ОШИБКА] Python не найден."
    echo " Установи: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
echo " Python $(python3 --version) найден."

# ── 2. Проверить .env ─────────────────────────────────────────────────
if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
        cp .env.example .env
        echo ""
        echo " [!] Файл .env создан из шаблона."
        echo "     Открой .env и заполни:"
        echo ""
        echo "       KRISHA_LOGIN           — телефон от krisha.kz"
        echo "       KRISHA_PASSWORD        — пароль от krisha.kz"
        echo "       TELEGRAM_BOT_TOKEN     — токен от @BotFather"
        echo "       TELEGRAM_ALLOWED_PHONES — твой номер телефона"
        echo ""
        echo " После заполнения запусти ./run.sh снова."
        echo ""
        if command -v xdg-open &>/dev/null; then
            xdg-open .env &
        fi
        exit 0
    else
        echo " [ОШИБКА] Нет файла .env и нет .env.example"
        exit 1
    fi
fi

# ── 3. Создать виртуальное окружение если нет ─────────────────────────
VENV=".venv"
if [[ ! -x "$VENV/bin/python" ]]; then
    echo ""
    echo " Создаю виртуальное окружение..."
    python3 -m venv "$VENV"
    echo " Готово."
fi

# ── 4. Установить зависимости если нужно ─────────────────────────────
if [[ ! -f "$VENV/.deps_installed" ]]; then
    echo ""
    echo " Устанавливаю зависимости (первый раз, займёт 1-3 мин)..."
    "$VENV/bin/pip" install --quiet -r requirements.txt
    echo " Зависимости установлены."

    echo ""
    echo " Устанавливаю браузер Chromium для Playwright..."
    "$VENV/bin/python" -m playwright install chromium
    echo " Chromium установлен."

    touch "$VENV/.deps_installed"
fi

# ── 5. Запустить бота ─────────────────────────────────────────────────
echo ""
echo " Запускаю бота..."
echo " (чтобы остановить — нажми Ctrl+C)"
echo ""

PYTHONPATH=. "$VENV/bin/python" telegram_bot.py
