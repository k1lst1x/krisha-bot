# krisha-bot

Бот для отправки сообщений продавцам на krisha.kz. Управление полностью через Telegram.

## Установка на новом ПК

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd krisha-bot
```

### 2. Создать `.env`

```bash
cp .env.example .env
```

Заполнить в `.env`:

| Переменная | Описание |
|---|---|
| `KRISHA_LOGIN` | Телефон от аккаунта krisha.kz |
| `KRISHA_PASSWORD` | Пароль от аккаунта krisha.kz |
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `TELEGRAM_ALLOWED_PHONES` | Твой номер телефона (кто может управлять ботом) |

### 3. Установить зависимости

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
python -m playwright install chromium
```

### 4. Запустить бота

```bash
PYTHONPATH=. python telegram_bot.py
```

Бот запущен. Открой чат с ботом в Telegram и нажми /menu.

---

## Docker (альтернатива)

```bash
cp .env.example .env
# заполнить .env

docker build -t krisha-bot .
docker run --env-file .env krisha-bot
```

---

## Использование

Всё управление через Telegram:

- **▶ Запустить поиск** — найти объявления и отправить сообщения
- **⚙ Настройки** — настроить город, фильтры, текст сообщения

Бот показывает прогресс в реальном времени и отчёт по завершении.  
Повторный запуск не пишет повторно тем же продавцам — все обработанные объявления сохраняются в `contacted.db`.

---

## Структура

| Файл | Назначение |
|---|---|
| `telegram_bot.py` | Точка входа — Telegram-бот (сервис) |
| `telegram_control.py` | Логика кнопок, настроек, запуска |
| `main.py` | Пайплайн: скрапинг → фильтры → отправка |
| `scraper.py` | Парсинг объявлений krisha.kz |
| `messenger.py` | Отправка сообщений через браузер (Playwright) |
| `listing_filters.py` | Фильтрация объявлений по параметрам |
| `config.json` | Текущие настройки (создаётся при первом запуске или через бота) |
| `contacted.db` | SQLite — история отправок (не коммитить) |
