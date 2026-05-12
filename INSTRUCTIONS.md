# ИНСТРУКЦИИ - Запуск krisha-bot

## 1. Требования

- Python 3.11+
- Аккаунт на krisha.kz
- OpenAI API ключ, если нужна генерация через API

## 2. Установка

```bash
cd krisha-bot
python -m venv .venv-linux
source .venv-linux/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Быстрый запуск одной командой (Linux):

```bash
./run.sh --limit 5
```

Скрипт `run.sh` при первом запуске сам создаст `.venv-linux`, установит зависимости и Chromium для Playwright.

## 3. Настройка `.env`

```env
OPENAI_API_KEY=sk-...
KRISHA_LOGIN=+77001234567
KRISHA_PASSWORD=yourpassword
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_POLL_TIMEOUT_SEC=0
TELEGRAM_RUN_TIMEOUT_SEC=900
TELEGRAM_ALLOWED_PHONES=+77001234567,+77017654321
TELEGRAM_MINI_APP_URL=https://your-domain.example/miniapp
TELEGRAM_MINI_APP_BIND=127.0.0.1
TELEGRAM_MINI_APP_PORT=8085
```

Если `OPENAI_API_KEY` пустой, бот использует локальный fallback-шаблон сообщения.
Для krisha.kz сейчас нужен номер телефона в `KRISHA_LOGIN`: форма входа на `id.kolesa.kz` показывает поле `Введите номер телефона`. Email на текущем flow не подходит для регистрации и может не пройти как логин.

Доступ к Telegram-командам:

- бот принимает команды только от авторизованных пользователей;
- пользователь должен отправить свой контакт через кнопку `Поделиться контактом`;
- номер сверяется с таблицей whitelist в SQLite;
- whitelist заполняется только из `TELEGRAM_ALLOWED_PHONES` (через запятую).
- после авторизации бот присылает кнопку `Открыть Mini App`;
- ссылка для кнопки берется из `TELEGRAM_MINI_APP_URL`.

## 4. Настройка `config.json`

```json
{
  "city": "karagandinskaja-oblast",
  "owner_type": 1,
  "categories": ["prodazha"],
  "rooms": [2, 3],
  "max_price_tenge": 50000000,
  "max_pages": 1,
  "max_messages_per_run": 20,
  "delay_between_messages_sec": 45,
  "request_delay_sec": 1.5,
  "goal": "Интересует ваш объект, хотим обсудить условия",
  "openai_model": "gpt-5.2",
  "max_message_chars": 450
}
```

Описание ключевых фильтров:

- `owner_type=1` - объявления от частников
- `rooms` - допустимое число комнат
- `max_price_tenge`/`min_price_tenge` - фильтр цены в тенге
- `location_keywords` - ключевые слова, которые должны встретиться в заголовке/районе объявления

## 5. Запуск

```bash
python main.py --dry-run
python main.py --limit 5
python main.py --dry-run --screenshots --limit 1
python main.py --dry-run --auth-screenshot --limit 0
python main.py --dry-run --screenshots --show-browser --limit 1
python main.py --telegram-sync-only
python telegram_bot.py
```

Реальная отправка пока не включена:

```bash
python main.py --send
```

Эта команда сейчас остановится с `NotImplementedError`, пока не завершена проверка формы сообщений.

## 6. Управление через Telegram Mini App

Запусти сервис:

```bash
PYTHONPATH=. python telegram_bot.py
```

`telegram_bot.py` поднимает:

- polling бота Telegram;
- встроенный HTTP Mini App сервер (`TELEGRAM_MINI_APP_BIND`/`TELEGRAM_MINI_APP_PORT`);
- API для настройки, запуска, статуса и кейсов.

Важно: держи запущенным только один экземпляр `telegram_bot.py` для одного токена, иначе Telegram вернет `409 Conflict` и часть нажатий кнопок будет теряться.

Поток пользователя:

- открыть чат бота и отправить контакт кнопкой `Поделиться контактом`;
- получить кнопку `Открыть Mini App`;
- в Mini App пройти пошаговую настройку или точный ручной ввод;
- запустить поиск (`x5`, `x10`, `x20`), проверять статус и при необходимости останавливать.

Что есть внутри Mini App:

- пошаговый мастер фильтров с кнопками и ручным вводом на каждом шаге;
- точный ручной редактор фильтров;
- настройка приветственного сообщения;
- запуск/статус/остановка;
- учет успешных кейсов.

Города в мастере подтягиваются с `krisha.kz` (раздел `prodazha/kvartiry`), при недоступности сайта используется fallback список.

Фон выполнения:

- запуск идет в фоне, бот не блокируется;
- в чат отправляется прогресс-сообщение с анимацией и потом удаляется;
- итоги и ошибки прилетают отдельным сообщением.

Продолжение со следующего объявления:

- обработанные `listing_id` пишутся в `contacted.db`;
- следующий запуск пропускает уже обработанные объявления.

Fallback-команды (если Mini App временно недоступен):

- `/menu` или `/open` - прислать кнопку Mini App;
- `/run krisha [limit]`, `/run status`, `/run stop`;
- `/settings`, `/message`, `/set <ключ> <значение>`;
- `/success_add [platform] <chat_link> <listing_url> [note]`, `/successes [N]`;
- `/help`.

Пример:

```text
/menu
/run krisha 5
/set max_price_tenge 47000000
/set rooms 2,3
/set categories prodazha
/set location_keywords карагандинская область,караганда
/set goal Интересует покупка, готовы обсудить детали
/success_add https://t.me/c/123/456 https://krisha.kz/a/show/100000 клиент согласен
/successes 10
```

## 7. Проверка

```bash
pytest
```

## 8. Расписание

Windows Task Scheduler:

```powershell
cd C:\path\to\krisha-bot
.\.venv\Scripts\python.exe main.py --dry-run
```

Linux cron:

```cron
0 10,15 * * * cd /path/to/krisha-bot && ./.venv/bin/python main.py --dry-run
```

## 9. Что смотреть

- `logs/activity.log` - действия и ошибки
- `logs/telegram-bot.log` - лог сервиса Telegram
- `contacted.db` - история контактов
- `logs/telegram_update_offset.txt` - смещение обработанных Telegram-команд
- `contacted.db` таблицы `telegram_allowed_contacts` и `telegram_authorized_users` - Telegram-доступ
- `contacted.db` таблица `telegram_success_events` - удачные кейсы (чат + ссылка)
