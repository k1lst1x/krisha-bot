from __future__ import annotations

from pathlib import Path

from telegram_control import (
    TelegramAccessStore,
    _parse_allowed_phones,
    get_or_create_telegram_controller,
    normalize_phone,
)


def test_normalize_phone_variants() -> None:
    assert normalize_phone("+7 (700) 123-45-67") == "+77001234567"
    assert normalize_phone("87001234567") == "+77001234567"
    assert normalize_phone("7001234567") == "+77001234567"


def test_normalize_phone_rejects_short_fragments() -> None:
    assert normalize_phone("+7") == ""
    assert normalize_phone("776") == ""


def test_parse_allowed_phones_handles_formatted_and_compact_lists() -> None:
    assert _parse_allowed_phones("+7 700 000 00 00, +77011112233 +77024445566") == [
        "+77000000000",
        "+77011112233",
        "+77024445566",
    ]


def test_access_store_authorizes_only_allowed_phone(tmp_path: Path) -> None:
    db_path = tmp_path / "test_access.db"
    store = TelegramAccessStore(db_path)

    store.seed_allowed_phones(["+77001234567"], source="test")
    assert store.is_phone_allowed("+7 700 123 45 67")
    assert not store.is_phone_allowed("+7 700 000 00 00")

    store.authorize_user(
        telegram_user_id=1234,
        chat_id="9876",
        phone="+7 700 123 45 67",
        username="demo",
        first_name="Demo",
    )
    assert store.is_user_authorized(telegram_user_id=1234, chat_id="9876")
    assert not store.is_user_authorized(telegram_user_id=1234, chat_id="1111")


def test_access_store_replace_allowed_phones_removes_old_env_entries(tmp_path: Path) -> None:
    db_path = tmp_path / "test_access_replace.db"
    store = TelegramAccessStore(db_path)

    store.seed_allowed_phones(["+77001234567"], source="test")
    store.authorize_user(
        telegram_user_id=1234,
        chat_id="9876",
        phone="+7 700 123 45 67",
        username="demo",
        first_name="Demo",
    )

    allowed_count, removed_count = store.replace_allowed_phones(["+77000000000"], source="env_bootstrap")

    assert allowed_count == 1
    assert removed_count == 1
    assert not store.is_phone_allowed("+7 700 123 45 67")
    assert store.is_phone_allowed("+7 700 000 00 00")
    assert not store.is_user_authorized(telegram_user_id=1234, chat_id="9876")


def test_access_store_user_input_state_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "test_access_state.db"
    store = TelegramAccessStore(db_path)

    store.set_user_input_state(
        telegram_user_id=1234,
        chat_id="9876",
        state_key="await:goal",
        state_payload={"foo": "bar"},
    )
    loaded = store.get_user_input_state(telegram_user_id=1234, chat_id="9876")
    assert loaded is not None
    assert loaded[0] == "await:goal"
    assert loaded[1]["foo"] == "bar"

    store.clear_user_input_state(telegram_user_id=1234, chat_id="9876")
    assert store.get_user_input_state(telegram_user_id=1234, chat_id="9876") is None


def test_get_or_create_controller_resyncs_whitelist_from_env_on_every_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    import telegram_control as tg_control

    tg_control._CONTROLLER_CACHE.clear()
    tg_control._ALLOWED_PHONES_ENV_CACHE.clear()
    tg_control._WHITELIST_EMPTY_WARNED.clear()

    calls: list[list[str]] = []
    original_replace = tg_control.TelegramAccessStore.replace_allowed_phones

    def counted_replace(self, phones: list[str], source: str = "env_bootstrap"):  # noqa: ANN001
        calls.append(list(phones))
        return original_replace(self, phones, source=source)

    monkeypatch.setattr(tg_control.TelegramAccessStore, "replace_allowed_phones", counted_replace)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    monkeypatch.setenv("TELEGRAM_ALLOWED_PHONES", "+7 700 000 00 00")
    monkeypatch.setenv("TELEGRAM_POLL_TIMEOUT_SEC", "0")
    monkeypatch.setenv("TELEGRAM_RUN_TIMEOUT_SEC", "900")

    first = get_or_create_telegram_controller(
        config_path=config_path,
        project_root=tmp_path,
        allow_run_command=False,
    )
    rogue_store = tg_control.TelegramAccessStore(tmp_path / "contacted.db")
    rogue_store.seed_allowed_phones(["+7 701 111 22 33"], source="manual")
    assert rogue_store.is_phone_allowed("+7 701 111 22 33")

    second = get_or_create_telegram_controller(
        config_path=config_path,
        project_root=tmp_path,
        allow_run_command=False,
    )

    assert first is not None
    assert second is not None
    assert len(calls) == 2
    assert not rogue_store.is_phone_allowed("+7 701 111 22 33")
