#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo ""
echo " ========================================="
echo "  Krisha Bot - Python 3.8 Selenium build"
echo " ========================================="
echo ""

if ! command -v python3 &>/dev/null; then
    echo " [ERROR] python3 was not found."
    exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info[:2] != (3, 8):
    raise SystemExit("This compatibility build must run on Python 3.8.x")
PY

VENV=".venv"
if [[ ! -x "$VENV/bin/python" ]]; then
    echo ""
    echo " Creating virtual environment..."
    python3 -m venv "$VENV"
fi

if [[ ! -f ".env" && -f ".env.example" ]]; then
    cp .env.example .env
    echo " Created .env from .env.example. Fill it and run again."
    exit 0
fi

if [[ ! -f "$VENV/.deps_installed" ]]; then
    echo ""
    echo " Installing dependencies..."
    "$VENV/bin/python" -m pip install --upgrade "pip<25" "setuptools<76" wheel
    "$VENV/bin/pip" install --quiet -r requirements.txt
    touch "$VENV/.deps_installed"
fi

echo ""
echo " Starting bot..."
PYTHONPATH=. "$VENV/bin/python" telegram_bot.py
