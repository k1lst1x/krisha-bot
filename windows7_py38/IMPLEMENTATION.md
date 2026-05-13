# Реализация совместимой версии

Эта папка содержит отдельную сборку проекта под Python 3.8 и Windows 7. Код в корне репозитория не меняется.

## Совместимость Python 3.8

Все основные модули используют `from __future__ import annotations`, поэтому современные аннотации вида `list[str]` и `Path | None` не вычисляются во время импорта и работают на Python 3.8.

Зависимости закреплены на версиях, которые устанавливаются под Python 3.8:

- `selenium==4.10.0`
- `pytest==7.4.4`
- `lxml==5.3.0`
- `beautifulsoup4==4.12.3`
- `requests==2.31.0`
- `python-dotenv==1.0.1`
- `urllib3==1.26.20`

## Selenium

`messenger.py` и `screenshotter.py` используют Selenium WebDriver вместо браузерного рантайма Playwright.

Поддержанные переменные:

- `KRISHA_CHROMEDRIVER` - полный путь к `chromedriver.exe`.
- `KRISHA_CHROME_BINARY` - полный путь к `chrome.exe`, если браузер не находится автоматически.
- `KRISHA_CHROME_PROFILE_DIR` - директория профиля Chrome для сохранения сессии krisha.kz.
- `KRISHA_HEADLESS` - `1/true/yes/on` для headless-режима, `0/false/no/off` для видимого окна.

Для Windows 7 лучше использовать Chrome/ChromeDriver `109`, потому что новые Chrome-линейки не предназначены для этой ОС.

## Поведение

- `main.py` оставляет dry-run режим по умолчанию.
- История отправок остается в `contacted.db`.
- Telegram-контроллер и Mini App API сохранены.
- Скриншоты категорий и страницы авторизации сохранены, но выполняются через Selenium.
- Реальная отправка по-прежнему требует валидных `KRISHA_LOGIN` и `KRISHA_PASSWORD`; если на стороне сайта появится captcha/2FA, код вернет понятную ошибку и не будет записывать отправку как успешную.

## Проверка

Полный локальный прогон:

```bat
set PYTHONPATH=.
.venv\Scripts\python -m pytest
```
