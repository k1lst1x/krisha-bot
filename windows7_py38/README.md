# krisha-bot Windows 7 / Python 3.8

Это отдельная совместимая копия проекта для компьютеров, где доступен только Python 3.8.x. Основная версия в корне репозитория не изменяется.

## Что изменено

- Требуемая версия Python: `3.8.x`.
- Playwright заменен на Selenium.
- Для браузерной автоматизации используется установленный Chrome/ChromeDriver.
- Dry-run, парсер, фильтры, Telegram-управление, база `contacted.db`, отчеты прогресса и упаковка оставлены с тем же поведением.

## Windows 7

1. Установить Python `3.8.10` и включить `Add Python to PATH`.
2. Установить Chrome `109` или другой Chromium-браузер, который реально запускается на Windows 7.
3. Положить подходящий `chromedriver.exe` рядом с проектом, добавить его в `PATH` или указать путь в `.env`:

```env
KRISHA_CHROMEDRIVER=C:\path\to\chromedriver.exe
KRISHA_CHROME_BINARY=C:\Program Files\Google\Chrome\Application\chrome.exe
```

Если `KRISHA_CHROMEDRIVER` пустой, Selenium попробует найти или скачать драйвер автоматически.

## Клиентский запуск

```bat
1_INSTALL_ONCE.bat
```

Первый файл запускается один раз: он проверит Python 3.8, создаст `.venv`, установит зависимости и создаст `.env`, если его нет. Заполни:

- `KRISHA_LOGIN`
- `KRISHA_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_PHONES`

После этого каждый обычный запуск:

```bat
2_RUN_BOT.bat
```

`start.bat` оставлен как старый совместимый запуск, но клиенту проще давать именно эти два файла.

## Ручная установка

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
set PYTHONPATH=.
.venv\Scripts\python telegram_bot.py
```

## Проверка

```bat
set PYTHONPATH=.
.venv\Scripts\python -m pytest
```

Live-проверки с реальными `.env` значениями:

```bat
set PYTHONPATH=.
set RUN_LIVE_SMOKE_TESTS=1
set RUN_BROWSER_SMOKE_TESTS=1
set RUN_KRISHA_LOGIN_SMOKE_TESTS=1
.venv\Scripts\python -m pytest tests\test_live_smoke.py
```

Эти проверки валидируют Telegram token, Selenium/Chrome и вход в krisha.kz. Сообщения продавцам они не отправляют.

## Структура

| Файл | Назначение |
|---|---|
| `telegram_bot.py` | Точка входа Telegram-бота |
| `telegram_control.py` | Кнопки, настройки, запуск процессов, Mini App API |
| `main.py` | Пайплайн: парсинг, фильтры, отправка/запись результата |
| `scraper.py` | HTTP-парсинг объявлений krisha.kz |
| `messenger.py` | Отправка сообщений через Selenium |
| `screenshotter.py` | Скриншоты страниц через Selenium |
| `listing_filters.py` | Фильтрация объявлений |
| `config.json` | Настройки поиска |
| `contacted.db` | SQLite-история отправок и Telegram-доступа |
