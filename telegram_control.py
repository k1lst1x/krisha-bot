from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


LOGGER = logging.getLogger(__name__)
DEFAULT_RUN_TIMEOUT_SEC = 900
SEND_MESSAGE_RETRIES = 2
RUN_PROGRESS_UPDATE_SEC = 2.0
RUN_RESULT_MARKER = "RESULT "
RUN_RESULT_BATCH_SIZE = 8
RUN_RESULT_BUTTONS_PER_ROW = 4
CITY_OPTIONS_CACHE_TTL_SEC = 60 * 60
CITY_LINK_RE = re.compile(r"/prodazha/kvartiry/([^/]+)/")
CITY_OPTIONS_FALLBACK = [
    {"slug": "karagandinskaja-oblast", "label": "Карагандинская обл."},
    {"slug": "karaganda", "label": "Караганда"},
    {"slug": "astana", "label": "Астана"},
    {"slug": "almaty", "label": "Алматы"},
]
CITY_SLUG_TO_LOCATION_KW: dict[str, str] = {
    "almaty": "алматы",
    "almatinskaja-oblast": "алматинская область,алматы",
    "astana": "астана",
    "shymkent": "шымкент",
    "karaganda": "карагандинская область,караганда",
    "karagandinskaja-oblast": "карагандинская область,караганда",
    "aktobe": "актобе",
    "aktobinskaja-oblast": "актюбинская область,актобе",
    "pavlodar": "павлодар",
    "pavlodarskaja-oblast": "павлодарская область,павлодар",
    "taraz": "тараз",
    "zhambylskaja-oblast": "жамбылская область,тараз",
    "ust-kamenogorsk": "усть-каменогорск",
    "vostochno-kazahstanskaja-oblast": "восточно-казахстанская область,усть-каменогорск",
    "semej": "семей",
    "atyrau": "атырау",
    "atyrausskaja-oblast": "атырауская область,атырау",
    "kostanaj": "костанай",
    "kostanajskaja-oblast": "костанайская область,костанай",
    "kokshetau": "кокшетау",
    "akmolinskaja-oblast": "акмолинская область,кокшетау",
    "petropavl": "петропавл",
    "severo-kazahstanskaja-oblast": "северо-казахстанская область,петропавл",
    "oral": "орал",
    "zapadno-kazahstanskaja-oblast": "западно-казахстанская область,орал",
    "aktau": "актау",
    "mangistauskaja-oblast": "мангистауская область,актау",
    "taldykorgan": "талдыкорган",
    "jetisuskaja-oblast": "жетысуская область,талдыкорган",
    "zhezkazgan": "жезказган",
    "temirtau": "темиртау",
    "balkhash": "балхаш",
    "ekibastuz": "экибастуз",
    "rudnyj": "рудный",
    "turkestan": "туркестан",
    "turkistanskaja-oblast": "туркестанская область,туркестан",
    "kentau": "кентау",
    "kapshagaj": "қапшағай",
    "stepnogorsk": "степногорск",
    "lisakovsk": "лисаковск",
    "arkalyk": "аркалык",
    "saryagash": "сарыагаш",
}
# (label, keyword_value) — quick district buttons shown in the location_keywords wizard step
CITY_DISTRICT_BUTTONS: dict[str, list[tuple[str, str]]] = {
    "almaty": [
        ("Бостандык", "бостандык"),
        ("Алатау", "алатауский"),
        ("Медеу", "медеу"),
        ("Ауэзов", "ауэзовский"),
        ("Наурызбай", "наурызбай"),
        ("Жетысу", "жетысу"),
        ("Турксиб", "турксиб"),
        ("Алмалы", "алмалы"),
    ],
    "almatinskaja-oblast": [
        ("Илийский р-н", "илийский"),
        ("Алматы", "алматы"),
        ("Капшагай", "капшагай"),
        ("Талдыкорган", "талдыкорган"),
        ("Текели", "текели"),
    ],
    "astana": [
        ("Есиль", "есиль"),
        ("Байконур", "байконур"),
        ("Алматинский р-н", "алматинский"),
        ("Сарыарка", "сарыарка"),
        ("Нура", "нура"),
    ],
    "karaganda": [
        ("Казыбек би", "казыбек би"),
        ("Октябрьский", "октябрьский"),
        ("Майкудук", "майкудук"),
        ("Михайловка", "михайловка"),
        ("Юго-Восток", "юго-восток"),
        ("Пришахтинск", "пришахтинск"),
    ],
    "karagandinskaja-oblast": [
        ("Майкудук", "майкудук"),
        ("Михайловка", "михайловка"),
        ("Темиртау", "темиртау"),
        ("Балхаш", "балхаш"),
        ("Жезказган", "жезказган"),
        ("Шахтинск", "шахтинск"),
    ],
    "shymkent": [
        ("Абай", "абай"),
        ("Аль-Фараби", "аль-фараби"),
        ("Каратау", "каратау"),
        ("Туран", "туран"),
        ("Енбекшинский", "енбекшинский"),
    ],
    "aktobe": [
        ("Астана", "астана"),
        ("Нур Актобе", "нур актобе"),
        ("Алматы", "алматы"),
        ("Центр", "центр"),
    ],
    "pavlodar": [
        ("Центр", "центр"),
        ("Кереку", "кереку"),
        ("Рабочий", "рабочий"),
    ],
    "ust-kamenogorsk": [
        ("Аблакетка", "аблакетка"),
        ("Центр", "центр"),
        ("Ульба", "ульба"),
        ("Левый берег", "левый берег"),
    ],
    "semej": [
        ("Центр", "центр"),
        ("Жана Семей", "жана семей"),
        ("Шугыла", "шугыла"),
    ],
}
RUN_PROGRESS_FRAMES = [" 🔍", " 🔍·", " 🔍··", " 🔍···", " 🔍····", " 🔍·····"]
SEARCH_WIZARD_STEPS = [
    "city",
    "owner",
    "categories",
    "rooms",
    "min_price",
    "max_price",
    "max_pages",
    "max_messages",
    "location_keywords",
]
ADVANCED_WIZARD_STEPS = [
    "floor_from",
    "floor_to",
    "not_first_floor",
    "building_floors_from",
    "building_floors_to",
    "area_from",
    "area_to",
    "kitchen_area_from",
    "kitchen_area_to",
    "year_built_from",
    "year_built_to",
    "text_search",
]
SETTING_KEY_MAPPING: dict[str, str] = {
    "city": "city",
    "owner": "owner_type",
    "categories": "categories",
    "rooms": "rooms",
    "min_price": "min_price_tenge",
    "max_price": "max_price_tenge",
    "max_pages": "max_pages",
    "max_messages": "max_messages_per_run",
    "location_keywords": "location_keywords",
    "goal": "goal",
    # Advanced
    "floor_from": "floor_from",
    "floor_to": "floor_to",
    "not_first_floor": "not_first_floor",
    "not_last_floor": "not_last_floor",
    "building_floors_from": "building_floors_from",
    "building_floors_to": "building_floors_to",
    "area_from": "area_from",
    "area_to": "area_to",
    "kitchen_area_from": "kitchen_area_from",
    "kitchen_area_to": "kitchen_area_to",
    "year_built_from": "year_built_from",
    "year_built_to": "year_built_to",
    "text_search": "text_search",
    "delay_messages": "delay_between_messages_sec",
    "fetch_details": "fetch_details",
}
SETTING_LABELS: dict[str, str] = {
    "city": "Город",
    "owner": "Тип владельца",
    "categories": "Категории",
    "rooms": "Комнаты",
    "min_price": "Мин. цена",
    "max_price": "Макс. цена",
    "max_pages": "Страниц",
    "max_messages": "Лимит за запуск",
    "location_keywords": "Локация",
    "goal": "Приветственное сообщение",
    # Advanced
    "floor_from": "Этаж от",
    "floor_to": "Этаж до",
    "not_first_floor": "Не первый этаж",
    "not_last_floor": "Не последний этаж",
    "building_floors_from": "Этажность дома от",
    "building_floors_to": "Этажность дома до",
    "area_from": "Площадь от (м²)",
    "area_to": "Площадь до (м²)",
    "kitchen_area_from": "Кухня от (м²)",
    "kitchen_area_to": "Кухня до (м²)",
    "year_built_from": "Год постройки от",
    "year_built_to": "Год постройки до",
    "text_search": "Поиск по тексту",
    "delay_messages": "Задержка между сообщениями (сек)",
    "fetch_details": "Загружать детали объявления",
}


def _fetch_city_options() -> list[dict[str, str]]:
    try:
        response = requests.get("https://krisha.kz/prodazha/kvartiry/", timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        found: list[dict[str, str]] = []
        seen: set[str] = set()
        for link in soup.select("a[href*='/prodazha/kvartiry/']"):
            href = str(link.get("href") or "")
            match = CITY_LINK_RE.search(href)
            if not match:
                continue
            slug = match.group(1).strip()
            if not slug or slug in seen:
                continue
            text = " ".join(link.get_text(" ", strip=True).split())
            label = text.replace("Продажа квартир в ", "").strip() if text else slug
            seen.add(slug)
            found.append({"slug": slug, "label": label})
        return found if found else CITY_OPTIONS_FALLBACK.copy()
    except Exception as exc:
        LOGGER.info("Failed to fetch city options from krisha.kz: %s", exc)
        return CITY_OPTIONS_FALLBACK.copy()


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone or "")
    if not digits:
        return ""

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits

    if len(digits) < 10 or len(digits) > 15:
        return ""

    return f"+{digits}"


def _parse_allowed_phones(raw_value: str) -> list[str]:
    phones = []
    seen = set()
    # Commas/semicolons/new lines allow formatted phones with spaces:
    # "+7 700 000 00 00, +7 701 111 22 33".
    for part in re.split(r"[,;\n]+", raw_value or ""):
        text = part.strip()
        if not text:
            continue

        candidates = [text]
        if not normalize_phone(text):
            candidates.extend(text.split())

        for candidate_raw in candidates:
            candidate = normalize_phone(candidate_raw.strip())
            if candidate and candidate not in seen:
                phones.append(candidate)
                seen.add(candidate)
    return phones


def _parse_int_or_none(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    if not text.isdigit():
        return None
    return int(text)


class TelegramAccessStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_allowed_contacts (
                    phone_e164 TEXT PRIMARY KEY,
                    added_at TEXT NOT NULL,
                    source TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_authorized_users (
                    telegram_user_id INTEGER PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    phone_e164 TEXT NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    authorized_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_user_input_state (
                    telegram_user_id INTEGER PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    state_key TEXT NOT NULL,
                    state_payload TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def seed_allowed_phones(self, phones: list[str], source: str = "bootstrap") -> int:
        inserted = 0
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            for raw_phone in phones:
                phone = normalize_phone(raw_phone)
                if not phone:
                    continue
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO telegram_allowed_contacts (phone_e164, added_at, source)
                    VALUES (?, ?, ?)
                    """,
                    (phone, now, source),
                )
                if cur.rowcount and cur.rowcount > 0:
                    inserted += 1
            conn.commit()
        finally:
            conn.close()
        return inserted

    def replace_allowed_phones(self, phones: list[str], source: str = "env_bootstrap") -> tuple[int, int]:
        normalized_phones = []
        seen = set()
        for raw_phone in phones:
            phone = normalize_phone(raw_phone)
            if phone and phone not in seen:
                normalized_phones.append(phone)
                seen.add(phone)

        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            before_rows = conn.execute("SELECT phone_e164 FROM telegram_allowed_contacts").fetchall()
            before_phones = {str(row[0]) for row in before_rows if row and row[0]}
            conn.execute("DELETE FROM telegram_allowed_contacts")
            for phone in normalized_phones:
                conn.execute(
                    """
                    INSERT INTO telegram_allowed_contacts (phone_e164, added_at, source)
                    VALUES (?, ?, ?)
                    """,
                    (phone, now, source),
                )
            conn.commit()
            after = len(normalized_phones)
        finally:
            conn.close()
        return after, len(before_phones - set(normalized_phones))

    def count_allowed_phones(self) -> int:
        conn = self._connect()
        try:
            row = conn.execute("SELECT COUNT(*) FROM telegram_allowed_contacts").fetchone()
        finally:
            conn.close()
        if row is None:
            return 0
        return int(row[0] or 0)

    def is_phone_allowed(self, phone: str) -> bool:
        normalized = normalize_phone(phone)
        if not normalized:
            return False

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM telegram_allowed_contacts WHERE phone_e164 = ? LIMIT 1",
                (normalized,),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    def authorize_user(
        self,
        telegram_user_id: int,
        chat_id: str,
        phone: str,
        username: str = "",
        first_name: str = "",
    ) -> None:
        normalized = normalize_phone(phone)
        if not normalized:
            raise ValueError("phone is empty after normalization")

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO telegram_authorized_users
                    (telegram_user_id, chat_id, phone_e164, username, first_name, authorized_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(telegram_user_id),
                    str(chat_id),
                    normalized,
                    username.strip(),
                    first_name.strip(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def is_user_authorized(self, telegram_user_id: int, chat_id: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT au.phone_e164
                FROM telegram_authorized_users au
                JOIN telegram_allowed_contacts ac
                    ON ac.phone_e164 = au.phone_e164
                WHERE au.telegram_user_id = ?
                  AND au.chat_id = ?
                LIMIT 1
                """,
                (int(telegram_user_id), str(chat_id)),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    def is_user_authorized_any_chat(self, telegram_user_id: int) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT 1
                FROM telegram_authorized_users au
                JOIN telegram_allowed_contacts ac
                    ON ac.phone_e164 = au.phone_e164
                WHERE au.telegram_user_id = ?
                LIMIT 1
                """,
                (int(telegram_user_id),),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    def get_authorized_chat_id(self, telegram_user_id: int) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT au.chat_id
                FROM telegram_authorized_users au
                JOIN telegram_allowed_contacts ac
                    ON ac.phone_e164 = au.phone_e164
                WHERE au.telegram_user_id = ?
                ORDER BY au.authorized_at DESC
                LIMIT 1
                """,
                (int(telegram_user_id),),
            ).fetchone()
        finally:
            conn.close()
        if not row or not row[0]:
            return None
        return str(row[0])

    def set_user_input_state(
        self,
        telegram_user_id: int,
        chat_id: str,
        state_key: str,
        state_payload: dict[str, Any] | None = None,
    ) -> None:
        payload_text = json.dumps(state_payload or {}, ensure_ascii=False)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO telegram_user_input_state
                    (telegram_user_id, chat_id, state_key, state_payload, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    int(telegram_user_id),
                    str(chat_id),
                    state_key.strip(),
                    payload_text,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_user_input_state(
        self,
        telegram_user_id: int,
        chat_id: str,
    ) -> tuple[str, dict[str, Any]] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT state_key, state_payload
                FROM telegram_user_input_state
                WHERE telegram_user_id = ?
                  AND chat_id = ?
                LIMIT 1
                """,
                (int(telegram_user_id), str(chat_id)),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None

        state_key = str(row[0])
        payload_raw = row[1] or "{}"
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return state_key, payload

    def clear_user_input_state(self, telegram_user_id: int, chat_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                DELETE FROM telegram_user_input_state
                WHERE telegram_user_id = ?
                  AND chat_id = ?
                """,
                (int(telegram_user_id), str(chat_id)),
            )
            conn.commit()
        finally:
            conn.close()


class TelegramSuccessStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_success_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    listing_url TEXT NOT NULL,
                    chat_link TEXT NOT NULL,
                    note TEXT,
                    created_by_user_id INTEGER,
                    created_by_chat_id TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def add_success(
        self,
        platform: str,
        listing_url: str,
        chat_link: str,
        note: str,
        created_by_user_id: int,
        created_by_chat_id: str,
    ) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO telegram_success_events
                    (created_at, platform, listing_url, chat_link, note, created_by_user_id, created_by_chat_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    platform.strip().lower(),
                    listing_url.strip(),
                    chat_link.strip(),
                    note.strip(),
                    int(created_by_user_id),
                    str(created_by_chat_id),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        safe_limit = max(1, min(30, int(limit)))
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT id, created_at, platform, listing_url, chat_link, note
                FROM telegram_success_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        finally:
            conn.close()

        return [
            {
                "id": row[0],
                "created_at": row[1],
                "platform": row[2],
                "listing_url": row[3],
                "chat_link": row[4],
                "note": row[5] or "",
            }
            for row in rows
        ]


class TelegramConfigController:
    def __init__(
        self,
        token: str,
        chat_id: str | None,
        config_path: Path,
        offset_path: Path,
        access_store: TelegramAccessStore,
        success_store: TelegramSuccessStore,
        project_root: Path,
        long_poll_timeout_sec: int = 0,
        run_timeout_sec: int = DEFAULT_RUN_TIMEOUT_SEC,
        allow_run_command: bool = False,
    ) -> None:
        self.token = token.strip()
        self.chat_id = str(chat_id).strip() if chat_id else ""
        self.config_path = config_path
        self.offset_path = offset_path
        self.access_store = access_store
        self.success_store = success_store
        self.project_root = project_root
        self.long_poll_timeout_sec = max(0, int(long_poll_timeout_sec))
        self.run_timeout_sec = max(60, int(run_timeout_sec))
        self.allow_run_command = allow_run_command
        self.session = requests.Session()
        self._city_options_lock = threading.Lock()
        self._city_options_cached: list[dict[str, str]] = CITY_OPTIONS_FALLBACK.copy()
        self._city_options_cached_at = 0.0
        self._run_state_lock = threading.RLock()
        self._active_run: subprocess.Popen[str] | None = None
        self._active_run_chat_id = ""
        self._active_run_started_at: datetime | None = None
        self._active_run_limit: int | None = None
        self._active_run_log_path: Path | None = None
        self._active_run_progress_message_id: int | None = None
        self._active_run_progress_frame = 0
        self._active_run_last_progress_update: datetime | None = None
        self._active_run_log_pos = 0
        self._active_run_seen_listing_ids: set[str] = set()
        self._active_run_result_count = 0
        self._active_run_sent_count = 0
        self._active_run_no_chat_count = 0
        self._active_run_failed_count = 0
        self._active_run_filter_skip_count = 0
        self._active_run_result_payloads: list[dict[str, Any]] = []
        self._active_run_is_dry_run = True

    def _is_run_active(self) -> bool:
        with self._run_state_lock:
            return self._active_run is not None and self._active_run.poll() is None

    def _city_options(self) -> list[dict[str, str]]:
        now = time.time()
        with self._city_options_lock:
            if now - self._city_options_cached_at < CITY_OPTIONS_CACHE_TTL_SEC and self._city_options_cached:
                return self._city_options_cached
        options = _fetch_city_options()
        with self._city_options_lock:
            self._city_options_cached = options
            self._city_options_cached_at = now
        return options

    def _run_logs_dir(self) -> Path:
        logs_dir = self.project_root / "logs" / "runs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    def _clear_run_state(self) -> None:
        self._active_run = None
        self._active_run_chat_id = ""
        self._active_run_started_at = None
        self._active_run_limit = None
        self._active_run_log_path = None
        self._active_run_progress_message_id = None
        self._active_run_progress_frame = 0
        self._active_run_last_progress_update = None
        self._active_run_log_pos = 0
        self._active_run_seen_listing_ids = set()
        self._active_run_result_count = 0
        self._active_run_sent_count = 0
        self._active_run_no_chat_count = 0
        self._active_run_failed_count = 0
        self._active_run_filter_skip_count = 0
        self._active_run_result_payloads = []
        self._active_run_is_dry_run = True

    def _parse_run_result_line(self, text: str) -> dict[str, Any] | None:
        marker_index = text.find(RUN_RESULT_MARKER)
        if marker_index < 0:
            return None

        payload_raw = text[marker_index + len(RUN_RESULT_MARKER) :].strip()
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _format_run_result_message(self, payload: dict[str, Any]) -> str:
        listing_id = str(payload.get("listing_id") or "").strip()
        status = str(payload.get("status") or "unknown").strip().lower()
        district = str(payload.get("district") or "").strip()
        price = str(payload.get("price") or "").strip()
        listing_url = str(payload.get("url") or "").strip()
        chat_url = str(payload.get("chat_url") or "").strip()
        response = str(payload.get("response") or "").strip()
        message = str(payload.get("message") or "").strip()

        status_label = {
            "sent": "отправлено",
            "dry_run": "dry-run",
            "skipped_no_chat": "пропуск: нет чата",
            "failed": "ошибка отправки",
        }.get(status, status)

        lines = [f"Объявление {listing_id or '(без id)'}: {status_label}"]
        if district:
            lines.append(f"Район: {district}")
        if price:
            lines.append(f"Цена: {price}")
        if listing_url:
            lines.append(f"Объявление: {listing_url}")
        if chat_url:
            lines.append(f"Чат: {chat_url}")
        if response and status in {"failed", "error", "skipped_no_chat"}:
            if len(response) > 400:
                response = f"{response[:397]}..."
            lines.append(f"Причина: {response}")
        if message:
            if len(message) > 260:
                message = f"{message[:257]}..."
            lines.append(f"Текст: {message}")
        return "\n".join(lines)

    def _drain_run_result_payloads(self) -> list[dict[str, Any]]:
        if not self._active_run_log_path or not self._active_run_log_path.exists():
            return []

        payloads: list[dict[str, Any]] = []
        try:
            with self._active_run_log_path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self._active_run_log_pos)
                for line in handle:
                    text = line.strip()

                    # Count filter-skipped listings from plain log lines
                    if "Skipping listing_id=" in text and "filter_reason=" in text:
                        self._active_run_filter_skip_count += 1
                        continue

                    payload = self._parse_run_result_line(text)
                    if payload is None:
                        continue

                    listing_id = str(payload.get("listing_id") or "").strip()
                    if listing_id:
                        if listing_id in self._active_run_seen_listing_ids:
                            continue
                        self._active_run_seen_listing_ids.add(listing_id)

                    self._active_run_result_count += 1
                    status = str(payload.get("status") or "").strip().lower()
                    if status == "sent":
                        self._active_run_sent_count += 1
                    elif status == "skipped_no_chat":
                        self._active_run_no_chat_count += 1
                    elif status == "failed":
                        self._active_run_failed_count += 1
                    payloads.append(payload)
                self._active_run_log_pos = handle.tell()
        except OSError:
            return []

        return payloads

    def _result_status_label(self, status: str) -> str:
        return {
            "sent": "отправлено",
            "dry_run": "dry-run",
            "skipped_no_chat": "нет чата",
            "failed": "ошибка",
        }.get(status, status)

    def _result_link(self, payload: dict[str, Any], prefer_chat: bool) -> str:
        if prefer_chat:
            chat_url = str(payload.get("chat_url") or "").strip()
            if chat_url.startswith("http"):
                return chat_url
        listing_url = str(payload.get("url") or "").strip()
        if listing_url.startswith("http"):
            return listing_url
        return ""

    @staticmethod
    def _clip_text(text: str, limit: int) -> str:
        normalized = " ".join((text or "").split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: max(0, limit - 3)]}..."

    def _send_result_batch(
        self,
        chat_id: str,
        title: str,
        entries: list[dict[str, Any]],
        include_reason: bool,
        prefer_chat_link: bool,
    ) -> None:
        if not entries:
            return

        for start in range(0, len(entries), RUN_RESULT_BATCH_SIZE):
            chunk = entries[start : start + RUN_RESULT_BATCH_SIZE]
            lines = [f"{title}: {len(entries)}"]
            if len(entries) > RUN_RESULT_BATCH_SIZE:
                part = (start // RUN_RESULT_BATCH_SIZE) + 1
                total_parts = (len(entries) + RUN_RESULT_BATCH_SIZE - 1) // RUN_RESULT_BATCH_SIZE
                lines.append(f"Часть {part}/{total_parts}")

            row: list[dict[str, str]] = []
            inline_rows: list[list[dict[str, str]]] = []
            for offset, payload in enumerate(chunk, start=start + 1):
                listing_id = str(payload.get("listing_id") or "").strip() or "?"
                district = self._clip_text(str(payload.get("district") or "").strip(), 72)
                status = str(payload.get("status") or "unknown").strip().lower()
                line = f"{offset}. #{listing_id} — {self._result_status_label(status)}"
                if district:
                    line = f"{line}, {district}"
                if include_reason and status == "failed":
                    reason = self._clip_text(str(payload.get("response") or "").strip(), 96)
                    # Only show non-generic errors to avoid cluttering the notification
                    generic = {"message button was not found", "message editor was not found"}
                    if reason and not any(g in reason.lower() for g in generic):
                        line = f"{line}\nПричина: {reason}"
                lines.append(line)

                url = self._result_link(payload, prefer_chat=prefer_chat_link)
                if url:
                    row.append({"text": str(offset), "url": url})
                    if len(row) >= RUN_RESULT_BUTTONS_PER_ROW:
                        inline_rows.append(row)
                        row = []

            if row:
                inline_rows.append(row)
            reply_markup = {"inline_keyboard": inline_rows} if inline_rows else None
            self._send_message(chat_id=chat_id, text="\n".join(lines), reply_markup=reply_markup)

    def _run_status_text(self) -> str:
        with self._run_state_lock:
            if not self._active_run:
                return "Сейчас активного запуска нет."

            return_code = self._active_run.poll()
            if return_code is None:
                started = self._active_run_started_at.isoformat() if self._active_run_started_at else "неизвестно"
                limit_text = str(self._active_run_limit) if self._active_run_limit is not None else "из config"
                log_text = str(self._active_run_log_path) if self._active_run_log_path else "нет"
                mode_text = "проверка (dry-run)" if self._active_run_is_dry_run else "реальная отправка"
                return (
                    "Поиск сейчас выполняется.\n"
                    f"Режим: {mode_text}\n"
                    f"Старт: {started}\n"
                    f"Лимит: {limit_text}\n"
                    f"Лог: {log_text}"
                )

            summary = self._build_run_summary(returncode=return_code, timed_out=False)
            self._delete_run_progress_message()
            self._clear_run_state()
            return summary

    def _stop_active_run(self) -> str:
        with self._run_state_lock:
            if not self._active_run or self._active_run.poll() is not None:
                self._clear_run_state()
                return "Активного запуска нет."

            try:
                self._active_run.terminate()
                self._active_run.wait(timeout=5)
            except Exception:
                try:
                    self._active_run.kill()
                except Exception:
                    pass
            summary = self._build_run_summary(returncode=-1, timed_out=True)
            self._delete_run_progress_message()
            self._clear_run_state()
            return f"Запуск остановлен пользователем.\n{summary}"

    def _poll_active_run(self) -> None:
        chat_id = ""
        result_payloads: list[dict[str, Any]] = []
        run_is_dry_run = True
        summary = ""
        with self._run_state_lock:
            if not self._active_run:
                return

            chat_id = self._active_run_chat_id
            new_payloads = self._drain_run_result_payloads()
            if new_payloads:
                self._active_run_result_payloads.extend(new_payloads)
            return_code = self._active_run.poll()
            timed_out = False
            if return_code is None and self._active_run_started_at is not None:
                elapsed = (datetime.now(timezone.utc) - self._active_run_started_at).total_seconds()
                if elapsed > self.run_timeout_sec:
                    timed_out = True
                    try:
                        self._active_run.kill()
                        return_code = self._active_run.wait(timeout=5)
                    except Exception:
                        return_code = -1

            if return_code is None:
                self._update_run_progress_message()
            else:
                result_payloads = self._active_run_result_payloads.copy()
                run_is_dry_run = self._active_run_is_dry_run
                summary = self._build_run_summary(returncode=return_code, timed_out=timed_out)
                self._delete_run_progress_message()
                self._clear_run_state()

        if chat_id and result_payloads:
            success_entries = [
                payload
                for payload in result_payloads
                if str(payload.get("status") or "").strip().lower() in {"sent", "dry_run"}
            ]
            failed_entries = [
                payload
                for payload in result_payloads
                if str(payload.get("status") or "").strip().lower()
                not in {"sent", "dry_run", "skipped_no_chat"}
            ]
            success_title = "✅ Проверено (dry-run)" if run_is_dry_run else "✅ Отправлено"
            self._send_result_batch(
                chat_id=chat_id,
                title=success_title,
                entries=success_entries,
                include_reason=False,
                prefer_chat_link=not run_is_dry_run,
            )
            self._send_result_batch(
                chat_id=chat_id,
                title="⚠ Не отправилось",
                entries=failed_entries,
                include_reason=True,
                prefer_chat_link=False,
            )

        if summary and chat_id:
            self._send_message(chat_id=chat_id, text=summary, reply_markup=self._main_menu_keyboard())

    def _run_progress_text(self) -> str:
        frame = RUN_PROGRESS_FRAMES[self._active_run_progress_frame % len(RUN_PROGRESS_FRAMES)]
        limit_text = str(self._active_run_limit) if self._active_run_limit is not None else "∞"
        lines = [f"Ищу объявления{frame}", f"▸ Лимит: {limit_text}"]
        if self._active_run_sent_count:
            lines.append(f"✅ Отправлено: {self._active_run_sent_count}")
        if self._active_run_no_chat_count:
            lines.append(f"🚫 Нет кнопки чата: {self._active_run_no_chat_count}")
        if self._active_run_failed_count:
            lines.append(f"⚠ Ошибок: {self._active_run_failed_count}")
        if self._active_run_filter_skip_count:
            lines.append(f"⏭ Пропущено фильтром: {self._active_run_filter_skip_count}")
        if not any([self._active_run_sent_count, self._active_run_no_chat_count,
                    self._active_run_failed_count, self._active_run_filter_skip_count]):
            lines.append("⏳ Сканирую...")
        return "\n".join(lines)

    def _update_run_progress_message(self) -> None:
        if not self._active_run_chat_id or not self._active_run_progress_message_id:
            return

        now = datetime.now(timezone.utc)
        if self._active_run_last_progress_update is not None:
            elapsed = (now - self._active_run_last_progress_update).total_seconds()
            if elapsed < RUN_PROGRESS_UPDATE_SEC:
                return

        self._active_run_progress_frame += 1
        self._active_run_last_progress_update = now
        self._edit_message_text(
            chat_id=self._active_run_chat_id,
            message_id=self._active_run_progress_message_id,
            text=self._run_progress_text(),
        )

    def _delete_run_progress_message(self) -> None:
        if not self._active_run_chat_id or not self._active_run_progress_message_id:
            return
        self._delete_message(
            chat_id=self._active_run_chat_id,
            message_id=self._active_run_progress_message_id,
        )

    def _build_run_summary(self, returncode: int, timed_out: bool) -> str:
        processed_count = 0
        sent_count = 0
        skipped_count = 0
        skipped_no_chat_count = 0
        failed_count = 0
        dry_run_count = 0
        tail_lines: deque[str] = deque(maxlen=4)

        if self._active_run_log_path and self._active_run_log_path.exists():
            try:
                with self._active_run_log_path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        text = line.strip()
                        if "Processed listing_id=" in text:
                            processed_count += 1
                            if "status=sent" in text:
                                sent_count += 1
                            elif "status=dry_run" in text:
                                dry_run_count += 1
                            elif "status=skipped_no_chat" in text:
                                skipped_no_chat_count += 1
                            elif "status=failed" in text:
                                failed_count += 1
                        if "Skipping listing_id=" in text:
                            skipped_count += 1
                        if text:
                            tail_lines.append(text)
            except OSError:
                pass

        mode = "проверка" if self._active_run_is_dry_run else "отправка"
        status_icon = "✅" if returncode == 0 and not timed_out else "⚠"

        parts: list[str] = []
        if sent_count:
            parts.append(f"отправлено: {sent_count}")
        if dry_run_count:
            parts.append(f"проверено: {dry_run_count}")
        if failed_count:
            parts.append(f"ошибок: {failed_count}")
        if skipped_count:
            parts.append(f"пропущено фильтром: {skipped_count}")

        stats = ", ".join(parts) if parts else "ничего не обработано"
        summary = f"{status_icon} Поиск завершён ({mode}). {stats}."

        if timed_out:
            summary = f"{summary}\nПревышен лимит времени ({self.run_timeout_sec} сек)."
        if returncode != 0 and tail_lines:
            summary = f"{summary}\nПоследнее: {tail_lines[-1][:200]}"
        return summary

    def sync_once(self) -> int:
        if not self.token:
            return 0

        self._poll_active_run()

        offset = self._load_offset()
        processed = 0
        last_seen_offset = offset

        try:
            updates = self._get_updates(offset=offset)
        except Exception as exc:
            LOGGER.warning("Failed to read Telegram updates: %s", exc)
            return 0

        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                last_seen_offset = max(last_seen_offset, update_id + 1)

            try:
                callback_query = update.get("callback_query")
                if isinstance(callback_query, dict):
                    handled = self._handle_callback_query(callback_query)
                    if handled:
                        processed += 1
                    continue

                message = update.get("message") or update.get("edited_message")
                if not isinstance(message, dict):
                    continue

                chat = message.get("chat", {})
                current_chat_id = str(chat.get("id", "")).strip()
                if not current_chat_id:
                    continue
                if self.chat_id and current_chat_id != self.chat_id:
                    continue

                from_user = message.get("from", {})
                user_id = from_user.get("id")
                if not isinstance(user_id, int):
                    continue

                contact = message.get("contact")
                if isinstance(contact, dict):
                    response = self._handle_contact(
                        chat_id=current_chat_id,
                        from_user=from_user,
                        contact=contact,
                    )
                    if response:
                        self._send_message(chat_id=current_chat_id, text=response)
                        if self.access_store.is_user_authorized(user_id, current_chat_id):
                            self._send_message(
                                chat_id=current_chat_id,
                                text="Главное меню:",
                                reply_markup=self._main_menu_keyboard(),
                            )
                    processed += 1
                    continue

                raw_text = message.get("text")
                if not isinstance(raw_text, str):
                    continue

                text = raw_text.strip()
                if not self.access_store.is_user_authorized(user_id, current_chat_id):
                    self._send_access_request(chat_id=current_chat_id)
                    processed += 1
                    continue

                if text.startswith("/"):
                    response = self._handle_command(
                        text=text,
                        chat_id=current_chat_id,
                        from_user=from_user,
                    )
                    if response:
                        self._send_message(chat_id=current_chat_id, text=response)
                else:
                    response, keyboard = self._handle_plain_text(
                        text=text,
                        chat_id=current_chat_id,
                        from_user=from_user,
                    )
                    if response:
                        self._send_message(
                            chat_id=current_chat_id,
                            text=response,
                            reply_markup=keyboard,
                        )
                processed += 1
            except Exception:
                LOGGER.exception("Failed to process Telegram update_id=%r", update_id)
                continue

        self._save_offset(last_seen_offset)
        self._poll_active_run()
        return processed

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def _get_updates(self, offset: int) -> list[dict[str, Any]]:
        poll_timeout = self.long_poll_timeout_sec
        if self._is_run_active() and poll_timeout > int(RUN_PROGRESS_UPDATE_SEC):
            poll_timeout = int(RUN_PROGRESS_UPDATE_SEC)
        params: dict[str, Any] = {"offset": offset, "timeout": poll_timeout}
        response = self.session.get(
            self._api_url("getUpdates"),
            params=params,
            timeout=(5, max(10, poll_timeout + 5)),
        )
        response.raise_for_status()

        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API error: {payload}")
        result = payload.get("result", [])
        if not isinstance(result, list):
            return []
        return result

    def _send_message(self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> int | None:
        data: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        for attempt in range(1, SEND_MESSAGE_RETRIES + 1):
            try:
                response = self.session.post(
                    self._api_url("sendMessage"),
                    data=data,
                    timeout=10,
                )
                response.raise_for_status()
                payload = response.json()
                result = payload.get("result", {}) if isinstance(payload, dict) else {}
                message_id = result.get("message_id") if isinstance(result, dict) else None
                return int(message_id) if isinstance(message_id, int) else None
            except Exception as exc:
                if attempt >= SEND_MESSAGE_RETRIES:
                    LOGGER.warning(
                        "Failed to send Telegram message after %s attempt(s): %s",
                        attempt,
                        exc,
                    )
                else:
                    LOGGER.info("Retrying Telegram sendMessage after transient error: %s", exc)
        return None

    def _edit_message_text(self, chat_id: str, message_id: int, text: str) -> None:
        try:
            response = self.session.post(
                self._api_url("editMessageText"),
                data={"chat_id": chat_id, "message_id": message_id, "text": text},
                timeout=10,
            )
            response.raise_for_status()
        except Exception as exc:
            LOGGER.info("Failed to edit Telegram progress message: %s", exc)

    def _delete_message(self, chat_id: str, message_id: int) -> None:
        try:
            response = self.session.post(
                self._api_url("deleteMessage"),
                data={"chat_id": chat_id, "message_id": message_id},
                timeout=10,
            )
            response.raise_for_status()
        except Exception as exc:
            LOGGER.info("Failed to delete Telegram progress message: %s", exc)

    def _answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:200]
        try:
            response = self.session.post(
                self._api_url("answerCallbackQuery"),
                data=payload,
                timeout=10,
            )
            response.raise_for_status()
        except Exception as exc:
            LOGGER.warning("Failed to answer callback query: %s", exc)

    def _main_menu_keyboard(self) -> dict[str, Any]:
        rows: list[list[dict[str, Any]]] = [
            [{"text": "▶ Запустить поиск", "callback_data": "menu:run"}],
            [{"text": "⚙ Настройки", "callback_data": "menu:settings"}],
        ]
        return {"inline_keyboard": rows}

    def _run_menu_keyboard(self) -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {"text": "Отправка x5", "callback_data": "run:send:5"},
                    {"text": "Отправка x10", "callback_data": "run:send:10"},
                    {"text": "Отправка x20", "callback_data": "run:send:20"},
                ],
                [
                    {"text": "Статус запуска", "callback_data": "run:status"},
                    {"text": "Остановить", "callback_data": "run:stop"},
                ],
                [
                    {"text": "Назад", "callback_data": "menu:main"},
                ],
            ]
        }

    def _settings_menu_keyboard(self) -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [{"text": "✍ Приветственное письмо", "callback_data": "menu:greeting"}],
                [{"text": "Основные настройки", "callback_data": "wizard:start"}],
                [{"text": "Расширенные фильтры", "callback_data": "advwiz:start"}],
                [{"text": "📋 Показать настройки", "callback_data": "menu:show"}],
                [{"text": "Назад", "callback_data": "menu:main"}],
            ]
        }

    def _greeting_menu_keyboard(self) -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {"text": "Базовое", "callback_data": "greet:set:base"},
                    {"text": "Покупка срочно", "callback_data": "greet:set:buy_fast"},
                ],
                [
                    {"text": "Ввести вручную", "callback_data": "greet:manual"},
                ],
                [
                    {"text": "Назад", "callback_data": "menu:main"},
                ],
            ]
        }

    def _greeting_menu_text(self) -> str:
        config = self._read_config()
        current_goal = str(config.get("goal", "")).strip() or "не задано"
        return (
            "Приветственное сообщение\n"
            "Это текст, который задает цель генерации сообщений.\n"
            f"Текущее: {current_goal}\n"
            "Выбери шаблон или введи свой вариант."
        )

    def _steps_for(self, step: str) -> list[str]:
        if step in ADVANCED_WIZARD_STEPS:
            return ADVANCED_WIZARD_STEPS
        return SEARCH_WIZARD_STEPS

    def _wizard_step_position(self, step: str) -> tuple[int, int]:
        steps = self._steps_for(step)
        if step not in steps:
            return 1, len(steps)
        return steps.index(step) + 1, len(steps)

    def _wizard_next_step(self, step: str) -> str | None:
        steps = self._steps_for(step)
        if step not in steps:
            return None
        index = steps.index(step)
        if index + 1 >= len(steps):
            return None
        return steps[index + 1]

    def _wizard_prev_step(self, step: str) -> str | None:
        steps = self._steps_for(step)
        if step not in steps:
            return None
        index = steps.index(step)
        if index <= 0:
            return None
        return steps[index - 1]

    def _wizard_step_title(self, step: str) -> str:
        titles = {
            "city": "Город поиска",
            "owner": "Тип владельца",
            "categories": "Категории объявлений",
            "rooms": "Комнаты",
            "min_price": "Минимальная цена",
            "max_price": "Максимальная цена",
            "max_pages": "Количество страниц",
            "max_messages": "Лимит за запуск",
            "location_keywords": "Ключевые слова локации",
            # Advanced
            "floor_from": "Этаж — от",
            "floor_to": "Этаж — до",
            "not_first_floor": "Не 1-й / не последний этаж",
            "building_floors_from": "Этажность дома — от",
            "building_floors_to": "Этажность дома — до",
            "area_from": "Общая площадь — от (м²)",
            "area_to": "Общая площадь — до (м²)",
            "kitchen_area_from": "Площадь кухни — от (м²)",
            "kitchen_area_to": "Площадь кухни — до (м²)",
            "year_built_from": "Год постройки — от",
            "year_built_to": "Год постройки — до",
            "text_search": "Поиск по тексту",
            "delay_messages": "Задержка между сообщениями (сек)",
            "fetch_details": "Загружать детали объявления",
        }
        return titles.get(step, step)

    def _wizard_step_hint(self, step: str) -> str:
        hints = {
            "city": "Например: karagandinskaja-oblast или karaganda.",
            "owner": "Частники обычно дают более прямой контакт.",
            "categories": "Продажа, аренда или оба направления.",
            "rooms": "Ограничь число комнат, чтобы убрать лишние объявления.",
            "min_price": "Нижняя граница цены. Можно пропустить.",
            "max_price": "Верхняя граница цены. Можно пропустить.",
            "max_pages": "Сколько страниц сканировать за один запуск.",
            "max_messages": "Сколько объявлений обработать за запуск.",
            "location_keywords": "Фильтр по ключевому слову в тексте объявления. Выбери район или введи вручную (пример: бостандык). Без фильтра — все объявления города.",
            # Advanced
            "floor_from": "Минимальный этаж квартиры. Пропусти, если не важно.",
            "floor_to": "Максимальный этаж квартиры. Пропусти, если не важно.",
            "not_first_floor": "Исключить крайние этажи. «Не 1-й» убирает первый, «Не последний» — верхний, «Оба» — оба сразу.",
            "building_floors_from": "Минимальная этажность дома. Пропусти, если не важно.",
            "building_floors_to": "Максимальная этажность дома. Пропусти, если не важно.",
            "area_from": "Минимальная общая площадь в м². Пропусти, если не важно.",
            "area_to": "Максимальная общая площадь в м². Пропусти, если не важно.",
            "kitchen_area_from": "Минимальная площадь кухни в м². Пропусти, если не важно.",
            "kitchen_area_to": "Максимальная площадь кухни в м². Пропусти, если не важно.",
            "year_built_from": "Год постройки не ранее. Пропусти, если не важно.",
            "year_built_to": "Год постройки не позднее. Пропусти, если не важно.",
            "text_search": "Слово или фраза в тексте объявления. Пропусти для отмены фильтра.",
            "delay_messages": "Пауза между отправкой сообщений, чтобы не попасть в спам (сек).",
            "fetch_details": "Загружать страницу объявления для точного парсинга — медленнее, но точнее.",
        }
        return hints.get(step, "")

    _WIZARD_REQUIRED_STEPS = frozenset({"city", "categories"})

    def _wizard_nav_row(self, step: str) -> list[dict[str, str]]:
        prefix = "advwiz" if step in ADVANCED_WIZARD_STEPS else "wiz"
        row: list[dict[str, str]] = []
        if self._wizard_prev_step(step):
            row.append({"text": "⬅ Назад", "callback_data": f"{prefix}:back:{step}"})
        if step not in self._WIZARD_REQUIRED_STEPS:
            row.append({"text": "Пропустить", "callback_data": f"{prefix}:skip:{step}"})
        row.append({"text": "Отмена", "callback_data": f"{prefix}:cancel"})
        return row

    def _wizard_step_keyboard(self, step: str) -> dict[str, Any]:
        rows: list[list[dict[str, str]]] = []

        if step == "city":
            cities = self._city_options()
            # Telegram inline keyboard allows max ~64 bytes per callback_data;
            # split cities into rows of 2 buttons each.
            city_rows = []
            pair: list[dict[str, str]] = []
            for city in cities:
                slug = city["slug"]
                label = city["label"]
                pair.append({"text": label, "callback_data": f"wiz:set:city:{slug}"})
                if len(pair) == 2:
                    city_rows.append(pair)
                    pair = []
            if pair:
                city_rows.append(pair)
            rows.extend(city_rows)
            rows.append([{"text": "Ввести вручную", "callback_data": "wiz:manual:city"}])
        elif step == "owner":
            rows.extend(
                [
                    [
                        {"text": "Частник (1)", "callback_data": "wiz:set:owner:1"},
                        {"text": "Крыша Агент", "callback_data": "wiz:set:owner:2"},
                    ],
                    [
                        {"text": "Без фильтра", "callback_data": "wiz:set:owner:none"},
                        {"text": "Ввести вручную", "callback_data": "wiz:manual:owner"},
                    ],
                ]
            )
        elif step == "categories":
            rows.extend(
                [
                    [
                        {"text": "Только продажа", "callback_data": "wiz:set:categories:prodazha"},
                        {"text": "Только аренда", "callback_data": "wiz:set:categories:arenda"},
                    ],
                    [
                        {"text": "Обе", "callback_data": "wiz:set:categories:prodazha,arenda"},
                        {"text": "Ввести вручную", "callback_data": "wiz:manual:categories"},
                    ],
                ]
            )
        elif step == "rooms":
            rows.extend(
                [
                    [
                        {"text": "1,2", "callback_data": "wiz:set:rooms:1,2"},
                        {"text": "2,3", "callback_data": "wiz:set:rooms:2,3"},
                        {"text": "3,4", "callback_data": "wiz:set:rooms:3,4"},
                    ],
                    [
                        {"text": "Только 2", "callback_data": "wiz:set:rooms:2"},
                        {"text": "Только 3", "callback_data": "wiz:set:rooms:3"},
                    ],
                    [
                        {"text": "Все комнаты", "callback_data": "wiz:set:rooms:none"},
                        {"text": "Ввести вручную", "callback_data": "wiz:manual:rooms"},
                    ],
                ]
            )
        elif step == "min_price":
            rows.extend(
                [
                    [
                        {"text": "10 млн", "callback_data": "wiz:set:min_price:10000000"},
                        {"text": "20 млн", "callback_data": "wiz:set:min_price:20000000"},
                        {"text": "30 млн", "callback_data": "wiz:set:min_price:30000000"},
                    ],
                    [
                        {"text": "Без минимума", "callback_data": "wiz:set:min_price:none"},
                    ],
                    [
                        {"text": "Ввести вручную", "callback_data": "wiz:manual:min_price"},
                    ],
                ]
            )
        elif step == "max_price":
            rows.extend(
                [
                    [
                        {"text": "40 млн", "callback_data": "wiz:set:max_price:40000000"},
                        {"text": "50 млн", "callback_data": "wiz:set:max_price:50000000"},
                        {"text": "60 млн", "callback_data": "wiz:set:max_price:60000000"},
                    ],
                    [
                        {"text": "Без максимума", "callback_data": "wiz:set:max_price:none"},
                    ],
                    [
                        {"text": "Ввести вручную", "callback_data": "wiz:manual:max_price"},
                    ],
                ]
            )
        elif step == "max_pages":
            rows.extend(
                [
                    [
                        {"text": "1", "callback_data": "wiz:set:max_pages:1"},
                        {"text": "2", "callback_data": "wiz:set:max_pages:2"},
                        {"text": "3", "callback_data": "wiz:set:max_pages:3"},
                    ],
                    [
                        {"text": "Ввести вручную", "callback_data": "wiz:manual:max_pages"},
                    ],
                ]
            )
        elif step == "max_messages":
            rows.extend(
                [
                    [
                        {"text": "5", "callback_data": "wiz:set:max_messages:5"},
                        {"text": "10", "callback_data": "wiz:set:max_messages:10"},
                        {"text": "20", "callback_data": "wiz:set:max_messages:20"},
                    ],
                    [
                        {"text": "Ввести вручную", "callback_data": "wiz:manual:max_messages"},
                    ],
                ]
            )
        elif step == "location_keywords":
            current_city_slug = ""
            try:
                current_city_slug = str(self._read_config().get("city", "") or "").strip().lower()
            except Exception:
                pass
            districts = CITY_DISTRICT_BUTTONS.get(current_city_slug, [])
            if districts:
                # Show district buttons 2 per row
                pair: list[dict[str, str]] = []
                for label, kw in districts:
                    pair.append({"text": label, "callback_data": f"wiz:set:location_keywords:{kw}"})
                    if len(pair) == 2:
                        rows.append(pair)
                        pair = []
                if pair:
                    rows.append(pair)
                rows.append([{"text": "Без фильтра", "callback_data": "wiz:set:location_keywords:none"}])
            elif current_city_slug and current_city_slug in CITY_SLUG_TO_LOCATION_KW:
                city_label = current_city_slug
                for opt in self._city_options():
                    if opt["slug"] == current_city_slug:
                        city_label = opt["label"]
                        break
                rows.append([
                    {"text": city_label, "callback_data": f"wiz:set:location_keywords:{current_city_slug}"},
                    {"text": "Без фильтра", "callback_data": "wiz:set:location_keywords:none"},
                ])
            else:
                rows.append([{"text": "Без фильтра", "callback_data": "wiz:set:location_keywords:none"}])
            rows.append([{"text": "Ввести вручную", "callback_data": "wiz:manual:location_keywords"}])

        elif step == "floor_from":
            rows.extend([
                [
                    {"text": "1", "callback_data": "advwiz:set:floor_from:1"},
                    {"text": "2", "callback_data": "advwiz:set:floor_from:2"},
                    {"text": "3", "callback_data": "advwiz:set:floor_from:3"},
                    {"text": "5", "callback_data": "advwiz:set:floor_from:5"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:floor_from"}],
            ])
        elif step == "floor_to":
            rows.extend([
                [
                    {"text": "5", "callback_data": "advwiz:set:floor_to:5"},
                    {"text": "10", "callback_data": "advwiz:set:floor_to:10"},
                    {"text": "15", "callback_data": "advwiz:set:floor_to:15"},
                    {"text": "20", "callback_data": "advwiz:set:floor_to:20"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:floor_to"}],
            ])
        elif step == "not_first_floor":
            rows.extend([
                [
                    {"text": "Не 1-й", "callback_data": "advwiz:set:not_first_floor:only_first"},
                    {"text": "Не последний", "callback_data": "advwiz:set:not_first_floor:only_last"},
                ],
                [
                    {"text": "Оба", "callback_data": "advwiz:set:not_first_floor:both"},
                    {"text": "Без ограничений", "callback_data": "advwiz:set:not_first_floor:none"},
                ],
            ])
        elif step == "building_floors_from":
            rows.extend([
                [
                    {"text": "5", "callback_data": "advwiz:set:building_floors_from:5"},
                    {"text": "9", "callback_data": "advwiz:set:building_floors_from:9"},
                    {"text": "12", "callback_data": "advwiz:set:building_floors_from:12"},
                    {"text": "16", "callback_data": "advwiz:set:building_floors_from:16"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:building_floors_from"}],
            ])
        elif step == "building_floors_to":
            rows.extend([
                [
                    {"text": "5", "callback_data": "advwiz:set:building_floors_to:5"},
                    {"text": "9", "callback_data": "advwiz:set:building_floors_to:9"},
                    {"text": "12", "callback_data": "advwiz:set:building_floors_to:12"},
                    {"text": "25", "callback_data": "advwiz:set:building_floors_to:25"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:building_floors_to"}],
            ])
        elif step == "area_from":
            rows.extend([
                [
                    {"text": "30 м²", "callback_data": "advwiz:set:area_from:30"},
                    {"text": "40 м²", "callback_data": "advwiz:set:area_from:40"},
                    {"text": "50 м²", "callback_data": "advwiz:set:area_from:50"},
                    {"text": "60 м²", "callback_data": "advwiz:set:area_from:60"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:area_from"}],
            ])
        elif step == "area_to":
            rows.extend([
                [
                    {"text": "60 м²", "callback_data": "advwiz:set:area_to:60"},
                    {"text": "80 м²", "callback_data": "advwiz:set:area_to:80"},
                    {"text": "100 м²", "callback_data": "advwiz:set:area_to:100"},
                    {"text": "150 м²", "callback_data": "advwiz:set:area_to:150"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:area_to"}],
            ])
        elif step == "kitchen_area_from":
            rows.extend([
                [
                    {"text": "6 м²", "callback_data": "advwiz:set:kitchen_area_from:6"},
                    {"text": "8 м²", "callback_data": "advwiz:set:kitchen_area_from:8"},
                    {"text": "10 м²", "callback_data": "advwiz:set:kitchen_area_from:10"},
                    {"text": "12 м²", "callback_data": "advwiz:set:kitchen_area_from:12"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:kitchen_area_from"}],
            ])
        elif step == "kitchen_area_to":
            rows.extend([
                [
                    {"text": "8 м²", "callback_data": "advwiz:set:kitchen_area_to:8"},
                    {"text": "10 м²", "callback_data": "advwiz:set:kitchen_area_to:10"},
                    {"text": "15 м²", "callback_data": "advwiz:set:kitchen_area_to:15"},
                    {"text": "20 м²", "callback_data": "advwiz:set:kitchen_area_to:20"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:kitchen_area_to"}],
            ])
        elif step == "year_built_from":
            rows.extend([
                [
                    {"text": "1980", "callback_data": "advwiz:set:year_built_from:1980"},
                    {"text": "1990", "callback_data": "advwiz:set:year_built_from:1990"},
                    {"text": "2000", "callback_data": "advwiz:set:year_built_from:2000"},
                    {"text": "2010", "callback_data": "advwiz:set:year_built_from:2010"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:year_built_from"}],
            ])
        elif step == "year_built_to":
            rows.extend([
                [
                    {"text": "2000", "callback_data": "advwiz:set:year_built_to:2000"},
                    {"text": "2010", "callback_data": "advwiz:set:year_built_to:2010"},
                    {"text": "2020", "callback_data": "advwiz:set:year_built_to:2020"},
                    {"text": "2025", "callback_data": "advwiz:set:year_built_to:2025"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:year_built_to"}],
            ])
        elif step == "text_search":
            rows.extend([
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:text_search"}],
            ])
        elif step == "delay_messages":
            rows.extend([
                [
                    {"text": "30 сек", "callback_data": "advwiz:set:delay_messages:30"},
                    {"text": "45 сек", "callback_data": "advwiz:set:delay_messages:45"},
                    {"text": "60 сек", "callback_data": "advwiz:set:delay_messages:60"},
                ],
                [{"text": "Ввести вручную", "callback_data": "advwiz:manual:delay_messages"}],
            ])
        elif step == "fetch_details":
            rows.extend([
                [
                    {"text": "Да (точнее, медленнее)", "callback_data": "advwiz:set:fetch_details:true"},
                    {"text": "Нет (быстрее)", "callback_data": "advwiz:set:fetch_details:false"},
                ],
            ])

        rows.append(self._wizard_nav_row(step))
        return {"inline_keyboard": rows}

    def _wizard_step_view(self, step: str) -> tuple[str, dict[str, Any]]:
        position, total = self._wizard_step_position(step)
        config_key = SETTING_KEY_MAPPING.get(step, "")
        config = self._read_config()
        current_value = config.get(config_key) if config_key else None
        title = self._wizard_step_title(step)
        hint = self._wizard_step_hint(step)
        label = "Расширенные настройки" if step in ADVANCED_WIZARD_STEPS else "Настройка поиска"
        text = (
            f"{label} - шаг {position}/{total}\n"
            f"{title}\n"
            f"{hint}\n"
            f"Текущее значение: {current_value!r}"
        )
        return text, self._wizard_step_keyboard(step)

    def _start_search_wizard(self, user_id: int, chat_id: str) -> tuple[str, dict[str, Any]]:
        first_step = SEARCH_WIZARD_STEPS[0]
        self.access_store.set_user_input_state(
            telegram_user_id=user_id,
            chat_id=chat_id,
            state_key="wizard:step",
            state_payload={"step": first_step},
        )
        return self._wizard_step_view(first_step)

    def _start_adv_wizard(self, user_id: int, chat_id: str) -> tuple[str, dict[str, Any]]:
        first_step = ADVANCED_WIZARD_STEPS[0]
        self.access_store.set_user_input_state(
            telegram_user_id=user_id,
            chat_id=chat_id,
            state_key="advwiz:step",
            state_payload={"step": first_step},
        )
        return self._wizard_step_view(first_step)

    def _handle_callback_query(self, callback_query: dict[str, Any]) -> bool:
        callback_id = str(callback_query.get("id", "")).strip()
        data = str(callback_query.get("data", "")).strip()
        from_user = callback_query.get("from", {})
        user_id = from_user.get("id")
        if not isinstance(user_id, int):
            if callback_id:
                self._answer_callback_query(callback_id)
            return False

        message = callback_query.get("message", {})
        if not isinstance(message, dict):
            if callback_id:
                self._answer_callback_query(callback_id)
            return False

        chat = message.get("chat", {})
        current_chat_id = str(chat.get("id", "")).strip()
        if not current_chat_id:
            if callback_id:
                self._answer_callback_query(callback_id)
            return False

        if self.chat_id and current_chat_id != self.chat_id:
            if callback_id:
                self._answer_callback_query(callback_id)
            return False

        if not self.access_store.is_user_authorized(user_id, current_chat_id):
            self._send_access_request(chat_id=current_chat_id)
            if callback_id:
                self._answer_callback_query(callback_id, "Нужна авторизация")
            return True

        if callback_id:
            self._answer_callback_query(callback_id)
        try:
            response_text, keyboard = self._handle_callback_data(
                data=data,
                chat_id=current_chat_id,
                from_user=from_user,
            )
        except Exception:
            LOGGER.exception("Failed to process callback data=%r", data)
            response_text = "Внутренняя ошибка обработки кнопки. Открой /menu и попробуй снова."
            keyboard = self._main_menu_keyboard()

        if response_text:
            self._send_message(chat_id=current_chat_id, text=response_text, reply_markup=keyboard)
        return True

    def _handle_plain_text(
        self,
        text: str,
        chat_id: str,
        from_user: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        user_id = from_user.get("id")
        if not isinstance(user_id, int):
            return "", None

        pending = self.access_store.get_user_input_state(user_id, chat_id)
        if pending is None:
            return (
                "Открой меню через /menu. Для справки: /help.",
                self._main_menu_keyboard(),
            )

        state_key, state_payload = pending
        try:
            if state_key in ("wizard:step", "advwiz:step"):
                step = str(state_payload.get("step", "")).strip()
                all_steps = ADVANCED_WIZARD_STEPS if state_key == "advwiz:step" else SEARCH_WIZARD_STEPS
                if step not in all_steps:
                    self.access_store.clear_user_input_state(user_id, chat_id)
                    return "Мастер настройки сброшен. Открой его снова через кнопку.", self._main_menu_keyboard()
                step_text, step_keyboard = self._wizard_step_view(step)
                return f"Выбери вариант кнопкой ниже.\n\n{step_text}", step_keyboard

            if state_key in ("wizard:manual", "advwiz:manual"):
                step = str(state_payload.get("step", "")).strip()
                all_steps = ADVANCED_WIZARD_STEPS if state_key == "advwiz:manual" else SEARCH_WIZARD_STEPS
                if step not in all_steps:
                    self.access_store.clear_user_input_state(user_id, chat_id)
                    return "Мастер настройки сброшен. Открой его снова через кнопку.", self._main_menu_keyboard()

                ok, save_message = self._apply_setting_value(step, text)
                if not ok:
                    return (
                        f"{save_message}\nПопробуй еще раз или нажми /cancel.",
                        self._wizard_manual_state_keyboard(step),
                    )
                return self._wizard_advance_after_step(
                    user_id=user_id,
                    chat_id=chat_id,
                    current_step=step,
                    prefix_text=save_message,
                )

            if state_key == "greet:manual":
                ok, save_message = self._apply_setting_value("goal", text)
                if not ok:
                    return f"{save_message}\nПопробуй еще раз или нажми /cancel.", None
                self.access_store.clear_user_input_state(user_id, chat_id)
                return f"{save_message}\n\n{self._greeting_menu_text()}", self._greeting_menu_keyboard()
        except Exception as exc:
            self.access_store.clear_user_input_state(user_id, chat_id)
            return f"Ошибка сохранения: {exc}", self._settings_menu_keyboard()

        self.access_store.clear_user_input_state(user_id, chat_id)
        return "Состояние ввода сброшено.", self._settings_menu_keyboard()

    def _handle_callback_data(
        self,
        data: str,
        chat_id: str,
        from_user: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        user_id = from_user.get("id")
        if not isinstance(user_id, int):
            return "", None

        if not data:
            return "", None

        if data == "menu:main":
            return "Главное меню:", self._main_menu_keyboard()
        if data == "menu:settings":
            return "Меню настроек:", self._settings_menu_keyboard()
        if data == "menu:run":
            return "Выбери лимит объявлений для запуска:", self._run_menu_keyboard()
        if data == "wizard:start":
            return self._start_search_wizard(user_id=user_id, chat_id=chat_id)
        if data == "advwiz:start":
            return self._start_adv_wizard(user_id=user_id, chat_id=chat_id)
        if data == "menu:greeting":
            return self._greeting_menu_text(), self._greeting_menu_keyboard()
        if data == "menu:show":
            return self._show_config(), self._main_menu_keyboard()
        if data == "menu:preset":
            return self._apply_preset("karaganda_sale"), self._main_menu_keyboard()
        if data == "menu:successes":
            return self._show_successes("10"), self._main_menu_keyboard()

        if data.startswith("wiz:"):
            return self._handle_wizard_callback_data(
                data=data,
                user_id=user_id,
                chat_id=chat_id,
            )

        if data.startswith("advwiz:"):
            return self._handle_adv_wizard_callback_data(
                data=data,
                user_id=user_id,
                chat_id=chat_id,
            )

        if data.startswith("greet:"):
            return self._handle_greeting_callback_data(
                data=data,
                user_id=user_id,
                chat_id=chat_id,
            )

        if data in ("run:kr5", "run:kr10", "run:kr20"):
            limit_map = {"run:kr5": "5", "run:kr10": "10", "run:kr20": "20"}
            return self._handle_callback_data(
                data=f"run:send:{limit_map[data]}", chat_id=chat_id, from_user=from_user
            )
        if data.startswith("run:send:") and not data.startswith("run:send:confirm:"):
            if not self.allow_run_command:
                return "Команда запуска доступна в telegram_bot.py.", self._main_menu_keyboard()
            limit_str = data.split(":", 2)[2]
            config = self._read_config()
            goal = str(config.get("goal") or "").strip() or "(сообщение не задано)"
            preview = goal if len(goal) <= 300 else goal[:297] + "..."
            keyboard = {"inline_keyboard": [
                [{"text": "✅ Подтвердить", "callback_data": f"run:send:confirm:{limit_str}"}],
                [{"text": "Отмена", "callback_data": "menu:run"}],
            ]}
            return f"Будет отправлено сообщение ({limit_str} шт.):\n\n{preview}", keyboard
        if data.startswith("run:send:confirm:"):
            if not self.allow_run_command:
                return "Команда запуска доступна в telegram_bot.py.", self._main_menu_keyboard()
            limit_str = data.split(":", 3)[3]
            try:
                limit = int(limit_str)
            except ValueError:
                limit = 10
            return self._run_krisha_process(limit=limit, chat_id=chat_id, dry_run=False), self._run_menu_keyboard()
        if data == "run:status":
            return self._run_status_text(), self._run_menu_keyboard()
        if data == "run:stop":
            return self._stop_active_run(), self._run_menu_keyboard()

        if data.startswith(("set:", "prompt:", "val:")):
            return (
                "Это старая кнопка из предыдущего меню. Открой /menu и продолжи через новые кнопки.",
                self._main_menu_keyboard(),
            )

        return "Неизвестная кнопка.", self._main_menu_keyboard()

    def _apply_button_value(self, data: str) -> str:
        parts = data.split(":", 2)
        if len(parts) != 3:
            return "Ошибка формата значения."
        _, key_token, raw_value = parts
        _, message = self._apply_setting_value(key_token=key_token, raw_value=raw_value)
        return message

    @staticmethod
    def _fmt_value(key_token: str, value: object) -> str:
        """Return a human-readable representation of a config value."""
        if value is None:
            return "не задано"
        if isinstance(value, bool):
            return "да" if value else "нет"
        if isinstance(value, list):
            labels = {
                "prodazha": "продажа", "arenda": "аренда",
                1: "частник", 2: "агент",
            }
            return ", ".join(str(labels.get(v, v)) for v in value)
        if key_token in ("min_price", "max_price", "min_price_tenge", "max_price_tenge"):
            try:
                n = int(value)
                if n >= 1_000_000:
                    return f"{n // 1_000_000} млн ₸"
                if n >= 1_000:
                    return f"{n // 1_000} тыс ₸"
                return f"{n} ₸"
            except (ValueError, TypeError):
                pass
        if key_token == "owner":
            return {"1": "частник", "2": "агент"}.get(str(value), str(value))
        return str(value)

    def _apply_setting_value(self, key_token: str, raw_value: str) -> tuple[bool, str]:
        # not_first_floor step controls both not_first_floor and not_last_floor in one click.
        if key_token == "not_first_floor":
            combos = {
                "only_first": (True, False),
                "only_last":  (False, True),
                "both":       (True, True),
                "none":       (False, False),
                "false":      (False, False),
            }
            nf, nl = combos.get(raw_value.strip().lower(), (False, False))
            config = self._read_config()
            config["not_first_floor"] = nf
            config["not_last_floor"] = nl
            self._write_config(config)
            parts = []
            if nf:
                parts.append("не 1-й")
            if nl:
                parts.append("не последний")
            label = "не 1-й / не последний"
            value_str = ", ".join(parts) if parts else "без ограничений"
            return True, f"✓ Сохранено — {label}: {value_str}"

        config_key = SETTING_KEY_MAPPING.get(key_token)
        if not config_key:
            return False, "Не удалось сохранить — неизвестный параметр."

        lowered_value = raw_value.strip().lower()
        if key_token == "owner":
            owner_aliases = {
                "частник": "1",
                "частники": "1",
                "owner": "1",
                "агентство": "2",
                "агент": "2",
                "agency": "2",
            }
            raw_value = owner_aliases.get(lowered_value, raw_value)
        if key_token == "categories":
            category_aliases = {
                "продажа": "prodazha",
                "купля": "prodazha",
                "аренда": "arenda",
                "съем": "arenda",
            }
            raw_value = ",".join(
                [category_aliases.get(part.strip().lower(), part.strip()) for part in raw_value.split(",")]
            )

        if key_token == "location_keywords":
            keyword_presets = {"kgd": "карагандинская область,караганда", "none": "none", **CITY_SLUG_TO_LOCATION_KW}
            raw_value = keyword_presets.get(raw_value, raw_value)
        if key_token == "goal":
            goal_presets = {
                "base": "Интересует ваш объект, хотим обсудить условия",
                "buy_fast": "Ищем покупку в ближайшее время, готовы обсудить условия",
            }
            raw_value = goal_presets.get(raw_value, raw_value)

        config = self._read_config()
        try:
            parsed = self._parse_value_for_key(config_key, raw_value)
        except ValueError as exc:
            return False, f"Неверное значение: {exc}"

        config[config_key] = parsed
        self._write_config(config)
        label = SETTING_LABELS.get(key_token, config_key)
        return True, f"✓ Сохранено — {label}: {self._fmt_value(key_token, parsed)}"

    def _skip_setting_value(self, key_token: str) -> tuple[bool, str]:
        if key_token == "not_first_floor":
            config = self._read_config()
            config["not_first_floor"] = False
            config["not_last_floor"] = False
            self._write_config(config)
            return True, "Пропущено — крайние этажи не фильтруются"

        config_key = SETTING_KEY_MAPPING.get(key_token)
        if not config_key:
            return False, "Не удалось пропустить — неизвестный параметр."

        defaults_by_key = {
            "owner_type": None,
            "rooms": None,
            "min_price_tenge": None,
            "max_price_tenge": None,
            "location_keywords": None,
            "floor_from": None,
            "floor_to": None,
            "not_first_floor": False,
            "not_last_floor": False,
            "building_floors_from": None,
            "building_floors_to": None,
            "area_from": None,
            "area_to": None,
            "kitchen_area_from": None,
            "kitchen_area_to": None,
            "year_built_from": None,
            "year_built_to": None,
            "text_search": None,
            "fetch_details": False,
            "max_pages": 1,
            "max_messages_per_run": 20,
            "delay_between_messages_sec": 45,
        }
        if config_key not in defaults_by_key:
            return True, f"Пропущено — {self._wizard_step_title(key_token)}"

        config = self._read_config()
        config[config_key] = defaults_by_key[config_key]
        self._write_config(config)
        label = SETTING_LABELS.get(key_token, config_key)
        return True, f"Пропущено — {label}"

    def _wizard_manual_prompt(self, step: str) -> str:
        prompts = {
            "city": "Введи city (пример: karagandinskaja-oblast).",
            "owner": "Введи owner_type: 1 (частник), 2 (Крыша Агент) или none.",
            "categories": "Введи категории через запятую (пример: prodazha,arenda).",
            "rooms": "Введи комнаты через запятую (пример: 2,3) или none.",
            "min_price": "Введи минимальную цену числом (пример: 20000000) или none.",
            "max_price": "Введи максимальную цену числом (пример: 50000000) или none.",
            "max_pages": "Введи целое число страниц (пример: 2).",
            "max_messages": "Введи лимит объявлений за запуск (пример: 10).",
            "location_keywords": "Введи ключевые слова через запятую (пример: караганда,майкудук).",
            # Advanced
            "floor_from": "Введи минимальный этаж числом (пример: 2) или none.",
            "floor_to": "Введи максимальный этаж числом (пример: 10) или none.",
            "building_floors_from": "Введи минимальную этажность дома числом (пример: 5) или none.",
            "building_floors_to": "Введи максимальную этажность дома числом (пример: 16) или none.",
            "area_from": "Введи минимальную площадь в м² (пример: 45) или none.",
            "area_to": "Введи максимальную площадь в м² (пример: 100) или none.",
            "kitchen_area_from": "Введи минимальную площадь кухни в м² (пример: 8) или none.",
            "kitchen_area_to": "Введи максимальную площадь кухни в м² (пример: 15) или none.",
            "year_built_from": "Введи минимальный год постройки (пример: 2000) или none.",
            "year_built_to": "Введи максимальный год постройки (пример: 2020) или none.",
            "text_search": "Введи слово для поиска в тексте объявления или none.",
            "delay_messages": "Введи задержку в секундах (пример: 45).",
        }
        return f"{prompts.get(step, 'Введи значение.')}\n\nЕсли передумал, нажми /cancel."

    def _wizard_manual_state_keyboard(self, step: str) -> dict[str, Any]:
        is_adv = step in ADVANCED_WIZARD_STEPS
        prefix = "advwiz" if is_adv else "wiz"
        return {
            "inline_keyboard": [
                [
                    {"text": "⬅ К вариантам шага", "callback_data": f"{prefix}:return:{step}"},
                ],
                [
                    {"text": "Отмена", "callback_data": f"{prefix}:cancel"},
                ],
            ]
        }

    def _wizard_advance_after_step(
        self,
        user_id: int,
        chat_id: str,
        current_step: str,
        prefix_text: str,
    ) -> tuple[str, dict[str, Any] | None]:
        is_advanced = current_step in ADVANCED_WIZARD_STEPS
        state_key = "advwiz:step" if is_advanced else "wizard:step"
        next_step = self._wizard_next_step(current_step)

        if not next_step:
            self.access_store.clear_user_input_state(user_id, chat_id)
            if is_advanced:
                return (
                    f"{prefix_text}\n\n"
                    "Расширенные настройки сохранены.\n"
                    "Теперь можно отправить сообщения.",
                    {
                        "inline_keyboard": [
                            [
                                {"text": "Отправить x5", "callback_data": "run:send:5"},
                                {"text": "Отправить x20", "callback_data": "run:send:20"},
                            ],
                            [{"text": "Главное меню", "callback_data": "menu:main"}],
                        ]
                    },
                )
            return (
                f"{prefix_text}\n\n"
                "Основные настройки сохранены.\n"
                "Можно отправить сообщения или настроить расширенные фильтры (этаж, площадь, год).",
                {
                    "inline_keyboard": [
                        [
                            {"text": "Отправить x5", "callback_data": "run:send:5"},
                            {"text": "Отправить x20", "callback_data": "run:send:20"},
                        ],
                        [
                            {"text": "Расширенные настройки", "callback_data": "advwiz:start"},
                            {"text": "Приветственное письмо", "callback_data": "menu:greeting"},
                        ],
                        [{"text": "Главное меню", "callback_data": "menu:main"}],
                    ]
                },
            )

        self.access_store.set_user_input_state(
            telegram_user_id=user_id,
            chat_id=chat_id,
            state_key=state_key,
            state_payload={"step": next_step},
        )
        next_text, next_keyboard = self._wizard_step_view(next_step)
        return f"{prefix_text}\n\n{next_text}", next_keyboard

    def _handle_wizard_callback_data(
        self,
        data: str,
        user_id: int,
        chat_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        if data == "wiz:cancel":
            self.access_store.clear_user_input_state(user_id, chat_id)
            return "Пошаговая настройка отменена.", self._main_menu_keyboard()

        if data.startswith("wiz:back:"):
            current_step = data.split(":", 2)[2].strip()
            prev_step = self._wizard_prev_step(current_step)
            if not prev_step:
                return self._wizard_step_view(current_step)
            self.access_store.set_user_input_state(
                telegram_user_id=user_id,
                chat_id=chat_id,
                state_key="wizard:step",
                state_payload={"step": prev_step},
            )
            return self._wizard_step_view(prev_step)

        if data.startswith("wiz:skip:"):
            current_step = data.split(":", 2)[2].strip()
            if current_step not in SEARCH_WIZARD_STEPS:
                return "Неизвестный шаг мастера.", self._main_menu_keyboard()
            ok, message = self._skip_setting_value(current_step)
            if not ok:
                return message, self._wizard_step_keyboard(current_step)
            return self._wizard_advance_after_step(
                user_id=user_id,
                chat_id=chat_id,
                current_step=current_step,
                prefix_text=message,
            )

        if data.startswith("wiz:manual:"):
            step = data.split(":", 2)[2].strip()
            if step not in SEARCH_WIZARD_STEPS:
                return "Неизвестный шаг мастера.", self._main_menu_keyboard()
            self.access_store.set_user_input_state(
                telegram_user_id=user_id,
                chat_id=chat_id,
                state_key="wizard:manual",
                state_payload={"step": step},
            )
            return self._wizard_manual_prompt(step), self._wizard_manual_state_keyboard(step)

        if data.startswith("wiz:return:"):
            step = data.split(":", 2)[2].strip()
            if step not in SEARCH_WIZARD_STEPS:
                return "Неизвестный шаг мастера.", self._main_menu_keyboard()
            self.access_store.set_user_input_state(
                telegram_user_id=user_id,
                chat_id=chat_id,
                state_key="wizard:step",
                state_payload={"step": step},
            )
            return self._wizard_step_view(step)

        if data.startswith("wiz:set:"):
            parts = data.split(":", 3)
            if len(parts) != 4:
                return "Ошибка формата шага.", self._main_menu_keyboard()
            _, _, step, raw_value = parts
            if step not in SEARCH_WIZARD_STEPS:
                return "Неизвестный шаг мастера.", self._main_menu_keyboard()
            ok, message = self._apply_setting_value(step, raw_value)
            if not ok:
                return message, self._wizard_step_keyboard(step)
            return self._wizard_advance_after_step(
                user_id=user_id,
                chat_id=chat_id,
                current_step=step,
                prefix_text=message,
            )

        return "Неизвестная кнопка мастера.", self._main_menu_keyboard()

    def _handle_adv_wizard_callback_data(
        self,
        data: str,
        user_id: int,
        chat_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        if data == "advwiz:cancel":
            self.access_store.clear_user_input_state(user_id, chat_id)
            return "Расширенная настройка отменена.", self._main_menu_keyboard()

        if data.startswith("advwiz:back:"):
            current_step = data.split(":", 2)[2].strip()
            if current_step not in ADVANCED_WIZARD_STEPS:
                return "Неизвестный шаг мастера.", self._main_menu_keyboard()
            prev_step = self._wizard_prev_step(current_step)
            if not prev_step:
                self.access_store.clear_user_input_state(user_id, chat_id)
                return "Начало расширенных настроек.", self._main_menu_keyboard()
            self.access_store.set_user_input_state(
                telegram_user_id=user_id,
                chat_id=chat_id,
                state_key="advwiz:step",
                state_payload={"step": prev_step},
            )
            return self._wizard_step_view(prev_step)

        if data.startswith("advwiz:skip:"):
            current_step = data.split(":", 2)[2].strip()
            if current_step not in ADVANCED_WIZARD_STEPS:
                return "Неизвестный шаг мастера.", self._main_menu_keyboard()
            ok, message = self._skip_setting_value(current_step)
            if not ok:
                return message, self._wizard_step_keyboard(current_step)
            return self._wizard_advance_after_step(
                user_id=user_id,
                chat_id=chat_id,
                current_step=current_step,
                prefix_text=message,
            )

        if data.startswith("advwiz:manual:"):
            step = data.split(":", 2)[2].strip()
            if step not in ADVANCED_WIZARD_STEPS:
                return "Неизвестный шаг мастера.", self._main_menu_keyboard()
            self.access_store.set_user_input_state(
                telegram_user_id=user_id,
                chat_id=chat_id,
                state_key="advwiz:manual",
                state_payload={"step": step},
            )
            return self._wizard_manual_prompt(step), self._wizard_manual_state_keyboard(step)

        if data.startswith("advwiz:return:"):
            step = data.split(":", 2)[2].strip()
            if step not in ADVANCED_WIZARD_STEPS:
                return "Неизвестный шаг мастера.", self._main_menu_keyboard()
            self.access_store.set_user_input_state(
                telegram_user_id=user_id,
                chat_id=chat_id,
                state_key="advwiz:step",
                state_payload={"step": step},
            )
            return self._wizard_step_view(step)

        if data.startswith("advwiz:set:"):
            parts = data.split(":", 3)
            if len(parts) != 4:
                return "Ошибка формата шага.", self._main_menu_keyboard()
            _, _, step, raw_value = parts
            if step not in ADVANCED_WIZARD_STEPS:
                return "Неизвестный шаг мастера.", self._main_menu_keyboard()
            ok, message = self._apply_setting_value(step, raw_value)
            if not ok:
                return message, self._wizard_step_keyboard(step)
            return self._wizard_advance_after_step(
                user_id=user_id,
                chat_id=chat_id,
                current_step=step,
                prefix_text=message,
            )

        return "Неизвестная кнопка расширенного мастера.", self._main_menu_keyboard()

    def _handle_greeting_callback_data(
        self,
        data: str,
        user_id: int,
        chat_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        if data == "greet:manual":
            self.access_store.set_user_input_state(
                telegram_user_id=user_id,
                chat_id=chat_id,
                state_key="greet:manual",
                state_payload={},
            )
            return "Отправь текст приветственного сообщения одним сообщением.", None

        if data.startswith("greet:set:"):
            preset = data.split(":", 2)[2].strip()
            ok, message = self._apply_setting_value("goal", preset)
            if not ok:
                return message, self._greeting_menu_keyboard()
            return f"{message}\n\n{self._greeting_menu_text()}", self._greeting_menu_keyboard()

        return self._greeting_menu_text(), self._greeting_menu_keyboard()

    def _send_access_request(self, chat_id: str) -> None:
        self._send_message(
            chat_id=chat_id,
            text=(
                "Доступ ограничен. Нажми кнопку ниже и отправь свой контакт.\n"
                "После подтверждения станет доступно меню управления ботом."
            ),
            reply_markup={
                "keyboard": [[{"text": "Поделиться контактом", "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )

    def _handle_contact(self, chat_id: str, from_user: dict[str, Any], contact: dict[str, Any]) -> str:
        user_id = from_user.get("id")
        if not isinstance(user_id, int):
            return "Не удалось определить пользователя."

        contact_user_id = contact.get("user_id")
        if isinstance(contact_user_id, int) and contact_user_id != user_id:
            return "Отправь, пожалуйста, именно свой контакт."

        phone = normalize_phone(str(contact.get("phone_number", "")))
        if not phone:
            return "Не удалось прочитать номер телефона. Попробуй еще раз."

        if not self.access_store.is_phone_allowed(phone):
            LOGGER.info("Telegram access denied for user_id=%s phone=%s", user_id, phone)
            return "Этот номер не найден в базе доступа."

        self.access_store.authorize_user(
            telegram_user_id=user_id,
            chat_id=chat_id,
            phone=phone,
            username=str(from_user.get("username", "")),
            first_name=str(from_user.get("first_name", "")),
        )
        return "Доступ подтвержден. Открой главное меню кнопкой ниже."

    def _handle_command(self, text: str, chat_id: str, from_user: dict[str, Any]) -> str:
        command, _, tail = text.partition(" ")
        command = command.split("@", 1)[0].lower()
        args = tail.strip()
        user_id = from_user.get("id")
        if isinstance(user_id, int) and command == "/cancel":
            self.access_store.clear_user_input_state(user_id, chat_id)
            return "Текущий ввод отменен."

        if command in {"/start", "/help"}:
            self._send_message(chat_id=chat_id, text="Главное меню:", reply_markup=self._main_menu_keyboard())
            return ""
        if command in {"/menu", "/open"}:
            self._send_message(chat_id=chat_id, text="Главное меню:", reply_markup=self._main_menu_keyboard())
            return ""
        if command == "/settings":
            if not isinstance(user_id, int):
                return "Не удалось определить пользователя."
            wizard_text, wizard_keyboard = self._start_search_wizard(user_id=user_id, chat_id=chat_id)
            self._send_message(chat_id=chat_id, text=wizard_text, reply_markup=wizard_keyboard)
            return ""
        if command == "/message":
            self._send_message(
                chat_id=chat_id,
                text=self._greeting_menu_text(),
                reply_markup=self._greeting_menu_keyboard(),
            )
            return ""
        if command == "/show":
            return self._show_config()
        if command == "/preset":
            return self._apply_preset(args)
        if command == "/set":
            return self._set_config_value(args)
        if command == "/run":
            if not self.allow_run_command:
                return "Команда /run доступна только в запущенном сервисе telegram_bot.py."
            return self._run_search(args=args, chat_id=chat_id)
        if command == "/success_add":
            return self._add_success(args=args, chat_id=chat_id, from_user=from_user)
        if command == "/successes":
            return self._show_successes(args=args)
        return "Неизвестная команда."

    def _show_config(self) -> str:
        config = self._read_config()

        def fmt(key: str) -> str:
            v = config.get(key)
            if v is None:
                return "—"
            return repr(v)

        sections: list[str] = ["Текущие настройки:\n"]

        # Basic
        sections.append("Основные:")
        sections.append(f"  Город: {fmt('city')}")
        sections.append(f"  Тип владельца: {fmt('owner_type')}")
        sections.append(f"  Категории: {fmt('categories')}")
        sections.append(f"  Комнаты: {fmt('rooms')}")
        sections.append(f"  Мин. цена: {fmt('min_price_tenge')}")
        sections.append(f"  Макс. цена: {fmt('max_price_tenge')}")
        sections.append(f"  Локация: {fmt('location_keywords')}")
        sections.append(f"  Страниц: {fmt('max_pages')}")
        sections.append(f"  Лимит за запуск: {fmt('max_messages_per_run')}")
        sections.append(f"  Цель/приветствие: {fmt('goal')}")

        # Advanced filters
        sections.append("\nРасширенные фильтры:")
        sections.append(f"  Этаж от: {fmt('floor_from')}")
        sections.append(f"  Этаж до: {fmt('floor_to')}")
        sections.append(f"  Не 1-й этаж: {fmt('not_first_floor')}")
        sections.append(f"  Не последний этаж: {fmt('not_last_floor')}")
        sections.append(f"  Этажность дома от: {fmt('building_floors_from')}")
        sections.append(f"  Этажность дома до: {fmt('building_floors_to')}")
        sections.append(f"  Площадь от (м²): {fmt('area_from')}")
        sections.append(f"  Площадь до (м²): {fmt('area_to')}")
        sections.append(f"  Кухня от (м²): {fmt('kitchen_area_from')}")
        sections.append(f"  Кухня до (м²): {fmt('kitchen_area_to')}")
        sections.append(f"  Год постройки от: {fmt('year_built_from')}")
        sections.append(f"  Год постройки до: {fmt('year_built_to')}")
        sections.append(f"  Поиск по тексту: {fmt('text_search')}")

        # Run settings
        sections.append("\nПараметры запуска:")
        sections.append(f"  Задержка между сообщениями (сек): {fmt('delay_between_messages_sec')}")
        sections.append(f"  Загружать детали: {fmt('fetch_details')}")

        return "\n".join(sections)

    def _apply_preset(self, preset_name: str) -> str:
        if preset_name.strip().lower() != "karaganda_sale":
            return "Неизвестный пресет."

        config = self._read_config()
        config.update(
            {
                "city": "karagandinskaja-oblast",
                "owner_type": 1,
                "categories": ["prodazha"],
                "rooms": [2, 3],
                "max_price_tenge": 50_000_000,
            }
        )
        self._write_config(config)
        return (
            "✓ Настройки обновлены — Карагандинская область:\n"
            "▸ Тип: частники\n"
            "▸ Категория: продажа\n"
            "▸ Комнаты: 2, 3\n"
            "▸ Макс. цена: 50 млн ₸"
        )

    def _set_config_value(self, args: str) -> str:
        parts = args.split(" ", maxsplit=1)
        if len(parts) != 2:
            return "Формат: /set <ключ> <значение>"

        key = parts[0].strip()
        raw_value = parts[1].strip()
        if not key:
            return "Ключ не указан."

        config = self._read_config()
        try:
            parsed_value = self._parse_value_for_key(key=key, raw_value=raw_value)
        except ValueError as exc:
            return f"Неверное значение для {key}: {exc}"

        config[key] = parsed_value
        self._write_config(config)
        label = SETTING_LABELS.get(key, key)
        return f"✓ Сохранено — {label}: {self._fmt_value(key, parsed_value)}"

    def _parse_value_for_key(self, key: str, raw_value: str) -> Any:
        lowered = raw_value.strip().lower()
        nullable = {"none", "null", "-", "off", "disable"}
        if lowered in nullable:
            return None

        if key in {
            "owner_type",
            "max_pages",
            "page_stop_below",
            "max_messages_per_run",
            "max_price_tenge",
            "min_price_tenge",
            "max_message_chars",
            "screenshot_pages",
            "screenshot_viewport_width",
            "screenshot_viewport_height",
            "telegram_poll_timeout_sec",
            "floor_from",
            "floor_to",
            "building_floors_from",
            "building_floors_to",
            "year_built_from",
            "year_built_to",
        }:
            return int(raw_value)

        if key in {"delay_between_messages_sec", "request_delay_sec", "area_from", "area_to", "kitchen_area_from", "kitchen_area_to"}:
            return float(raw_value)

        if key in {"fetch_details", "not_first_floor", "not_last_floor"}:
            return lowered in {"1", "true", "yes", "on", "y", "да"}

        if key in {"categories", "location_keywords"}:
            return [part.strip() for part in raw_value.split(",") if part.strip()]

        if key == "rooms":
            rooms = []
            for chunk in raw_value.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                rooms.append(int(chunk))
            if not rooms:
                raise ValueError("нужны значения вида 2,3")
            return rooms

        return raw_value

    def _run_search(self, args: str, chat_id: str) -> str:
        parts = [part for part in args.split(" ") if part.strip()]
        if not parts:
            parts = ["krisha"]

        platform = parts[0].strip().lower()
        if platform in {"status", "state"}:
            return self._run_status_text()
        if platform in {"stop", "cancel"}:
            return self._stop_active_run()
        if platform in {"hh", "headhunter"}:
            return "Поиск по HeadHunter пока не реализован в этом проекте. Сейчас доступно: /run krisha [limit]."

        if platform not in {"krisha", "kz", "krisha.kz"}:
            return "Неизвестная команда. Используй /run krisha [limit], /run status или /run stop."

        limit: int | None = None
        dry_run = True
        for raw_part in parts[1:]:
            token = raw_part.strip().lower()
            if token in {"send", "live", "real"}:
                dry_run = False
                continue
            parsed_limit = _parse_int_or_none(token)
            if parsed_limit is None:
                return "Неверный формат. Пример: /run krisha 5 или /run krisha send 5"
            limit = max(1, min(200, parsed_limit))

        return self._run_krisha_process(limit=limit, chat_id=chat_id, dry_run=dry_run)

    def _run_krisha_process(self, limit: int | None, chat_id: str, dry_run: bool = True) -> str:
        with self._run_state_lock:
            if self._active_run and self._active_run.poll() is None:
                return (
                    "Поиск уже выполняется.\n"
                    "Открой 'Статус запуска' или используй /run status.\n"
                    "Если нужно остановить - кнопка 'Остановить' или /run stop."
                )

            command = [
                sys.executable,
                str(self.project_root / "main.py"),
                "--no-telegram-sync",
                "--config",
                str(self.config_path),
            ]
            if dry_run:
                command.append("--dry-run")
            else:
                command.append("--send")
            if limit is not None:
                command.extend(["--limit", str(limit)])

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            run_limit_text = str(limit) if limit is not None else "config"
            log_path = self._run_logs_dir() / f"krisha-run-{timestamp}.log"

            try:
                with log_path.open("w", encoding="utf-8") as log_handle:
                    process = subprocess.Popen(
                        command,
                        cwd=self.project_root,
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        text=True,
                        close_fds=True,
                    )
            except Exception as exc:
                return f"Не удалось запустить поиск: {exc}"

            self._active_run = process
            self._active_run_chat_id = chat_id
            self._active_run_started_at = datetime.now(timezone.utc)
            self._active_run_limit = limit
            self._active_run_log_path = log_path
            self._active_run_progress_frame = 0
            self._active_run_last_progress_update = datetime.now(timezone.utc)
            self._active_run_log_pos = 0
            self._active_run_seen_listing_ids = set()
            self._active_run_result_count = 0
            self._active_run_result_payloads = []
            self._active_run_is_dry_run = dry_run
            self._active_run_progress_message_id = self._send_message(
                chat_id=chat_id,
                text=self._run_progress_text(),
            )

            if self._active_run_progress_message_id:
                return ""
            return (
                "Запуск принят.\n"
                f"Лимит: {run_limit_text}\n"
                f"Лог: {log_path}\n"
                "Бот остается на связи. По завершению я отправлю итог автоматически."
            )

    def _add_success(self, args: str, chat_id: str, from_user: dict[str, Any]) -> str:
        parts = [part for part in args.split(" ") if part.strip()]
        if len(parts) < 2:
            return (
                "Формат: /success_add [platform] <chat_link> <listing_url> [note]. "
                "Пример: /success_add krisha https://t.me/c/1/2 https://krisha.kz/a/show/123 клиент согласен"
            )

        known_platforms = {"krisha", "hh", "headhunter"}
        if parts[0].lower() in known_platforms:
            if len(parts) < 3:
                return "Недостаточно аргументов. Нужны platform, chat_link, listing_url."
            platform = parts[0].lower()
            chat_link = parts[1]
            listing_url = parts[2]
            note = " ".join(parts[3:]) if len(parts) > 3 else ""
        else:
            platform = "krisha"
            chat_link = parts[0]
            listing_url = parts[1]
            note = " ".join(parts[2:]) if len(parts) > 2 else ""

        if not chat_link.startswith("http"):
            return "chat_link должен начинаться с http/https."
        if not listing_url.startswith("http"):
            return "listing_url должен начинаться с http/https."

        user_id = from_user.get("id")
        if not isinstance(user_id, int):
            return "Не удалось определить user_id."

        event_id = self.success_store.add_success(
            platform=platform,
            listing_url=listing_url,
            chat_link=chat_link,
            note=note,
            created_by_user_id=user_id,
            created_by_chat_id=chat_id,
        )
        return f"Успешный кейс сохранен: id={event_id}"

    def _show_successes(self, args: str) -> str:
        limit = _parse_int_or_none(args) or 10
        rows = self.success_store.list_recent(limit=limit)
        if not rows:
            return "Пока нет сохраненных удачных кейсов."

        lines = ["Последние удачные кейсы:"]
        for row in rows:
            lines.append(
                f"#{row['id']} [{row['platform']}] {row['created_at']} | chat={row['chat_link']} | listing={row['listing_url']} | note={row['note']}"
            )
        return "\n".join(lines)

    def _read_config(self) -> dict[str, Any]:
        with self.config_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Config payload is not an object")
        return payload

    def _write_config(self, config: dict[str, Any]) -> None:
        with self.config_path.open("w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    def _load_offset(self) -> int:
        try:
            text = self.offset_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return 0
        except OSError:
            return 0

        if not text:
            return 0
        try:
            return int(text)
        except ValueError:
            return 0

    def _save_offset(self, offset: int) -> None:
        self.offset_path.parent.mkdir(parents=True, exist_ok=True)
        self.offset_path.write_text(str(offset), encoding="utf-8")


_CONTROLLER_CACHE: dict[str, TelegramConfigController] = {}
_ALLOWED_PHONES_ENV_CACHE: dict[str, tuple[str, ...]] = {}
_WHITELIST_EMPTY_WARNED: set[str] = set()


def get_or_create_telegram_controller(
    config_path: Path,
    project_root: Path,
    allow_run_command: bool = False,
) -> TelegramConfigController | None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        return None

    try:
        poll_timeout = int(os.getenv("TELEGRAM_POLL_TIMEOUT_SEC", "0"))
    except ValueError:
        poll_timeout = 0

    try:
        run_timeout_sec = int(os.getenv("TELEGRAM_RUN_TIMEOUT_SEC", str(DEFAULT_RUN_TIMEOUT_SEC)))
    except ValueError:
        run_timeout_sec = DEFAULT_RUN_TIMEOUT_SEC

    access_store = TelegramAccessStore(project_root / "contacted.db")
    success_store = TelegramSuccessStore(project_root / "contacted.db")

    bootstrap_phones = _parse_allowed_phones(os.getenv("TELEGRAM_ALLOWED_PHONES", ""))
    env_cache_key = str(project_root.resolve())
    env_snapshot = tuple(bootstrap_phones)
    allowed_count, removed_count = access_store.replace_allowed_phones(bootstrap_phones, source="env_bootstrap")
    if _ALLOWED_PHONES_ENV_CACHE.get(env_cache_key) != env_snapshot:
        _ALLOWED_PHONES_ENV_CACHE[env_cache_key] = env_snapshot
        if bootstrap_phones:
            LOGGER.info(
                "Synced %s allowed Telegram phone(s) from env; removed=%s",
                allowed_count,
                removed_count,
            )
    elif removed_count > 0:
        LOGGER.warning(
            "Whitelist store was resynced to .env; removed non-env phones=%s",
            removed_count,
        )

    allowed_now = access_store.count_allowed_phones()
    if allowed_now == 0:
        if env_cache_key not in _WHITELIST_EMPTY_WARNED:
            LOGGER.warning(
                "Telegram access whitelist is empty. Set TELEGRAM_ALLOWED_PHONES in .env "
                "to allow authorization via contact sharing."
            )
            _WHITELIST_EMPTY_WARNED.add(env_cache_key)
    else:
        _WHITELIST_EMPTY_WARNED.discard(env_cache_key)

    cache_key = "|".join(
        [
            str(project_root.resolve()),
            str(config_path.resolve()),
            token,
            chat_id,
            "run" if allow_run_command else "sync",
        ]
    )
    controller = _CONTROLLER_CACHE.get(cache_key)
    if controller is None:
        controller = TelegramConfigController(
            token=token,
            chat_id=chat_id or None,
            config_path=config_path,
            offset_path=project_root / "logs" / "telegram_update_offset.txt",
            access_store=access_store,
            success_store=success_store,
            project_root=project_root,
            long_poll_timeout_sec=poll_timeout,
            run_timeout_sec=run_timeout_sec,
            allow_run_command=allow_run_command,
        )
        _CONTROLLER_CACHE[cache_key] = controller
    else:
        controller.long_poll_timeout_sec = max(0, int(poll_timeout))
        controller.run_timeout_sec = max(60, int(run_timeout_sec))
        controller.allow_run_command = allow_run_command
        controller.access_store = access_store
        controller.success_store = success_store

    return controller


def sync_config_from_telegram(
    config_path: Path,
    project_root: Path,
    allow_run_command: bool = False,
) -> int:
    controller = get_or_create_telegram_controller(
        config_path=config_path,
        project_root=project_root,
        allow_run_command=allow_run_command,
    )
    if controller is None:
        return 0
    return controller.sync_once()
