# Инструкции для Windows 7 / Python 3.8

## Требования

- Windows 7 SP1.
- Python `3.8.10`.
- Chrome `109` и совместимый `chromedriver.exe`.
- Аккаунт krisha.kz.
- Telegram bot token.

## Настройка `.env`

```env
KRISHA_LOGIN=+77001234567
KRISHA_PASSWORD=yourpassword
KRISHA_CHROMEDRIVER=C:\path\to\chromedriver.exe
KRISHA_CHROME_BINARY=
KRISHA_CHROME_PROFILE_DIR=.krisha_chrome_profile
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_PHONES=+77001234567,+77017654321
TELEGRAM_POLL_TIMEOUT_SEC=20
TELEGRAM_RUN_TIMEOUT_SEC=900
```

`KRISHA_CHROMEDRIVER` можно оставить пустым, если `chromedriver.exe` лежит в `PATH` или Selenium Manager смог скачать драйвер сам. Для клиентской Windows 7 надежнее указать путь явно.

## Установка для клиента

Один раз:

```bat
1_INSTALL_ONCE.bat
```

Потом каждый запуск:

```bat
2_RUN_BOT.bat
```

`1_INSTALL_ONCE.bat` создает `.venv`, ставит зависимости и создает `.env`, если его нет. `2_RUN_BOT.bat` проверяет `.env`, ChromeDriver path и запускает Telegram-бота.

## Ручная установка

```bat
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade "pip<25" "setuptools<76" wheel
.venv\Scripts\pip install -r requirements.txt
```

## Запуск

```bat
set PYTHONPATH=.
.venv\Scripts\python telegram_bot.py
```

Или старым одним кликом:

```bat
start.bat
```

## Проверка

```bat
set PYTHONPATH=.
.venv\Scripts\python -m pytest
```

Live-smoke без отправки сообщений:

```bat
set PYTHONPATH=.
set RUN_LIVE_SMOKE_TESTS=1
set RUN_BROWSER_SMOKE_TESTS=1
set RUN_KRISHA_LOGIN_SMOKE_TESTS=1
.venv\Scripts\python -m pytest tests\test_live_smoke.py
```

## Команды

```bat
.venv\Scripts\python main.py --dry-run
.venv\Scripts\python main.py --limit 5
.venv\Scripts\python main.py --dry-run --screenshots --limit 1
.venv\Scripts\python main.py --dry-run --auth-screenshot --limit 0
.venv\Scripts\python main.py --send
```

По умолчанию запуск безопасный: без `--send` сообщения не отправляются.
