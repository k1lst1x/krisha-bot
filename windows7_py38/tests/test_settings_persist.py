"""
End-to-end: every wizard step writes the correct value to config.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from telegram_control import TelegramAccessStore, TelegramConfigController, TelegramSuccessStore

FROM_USER = {"id": 42}
CHAT_ID = "999"


def _build(tmp_path: Path) -> TelegramConfigController:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "city": "old-city",
                "owner_type": None,
                "categories": ["arenda"],
                "rooms": None,
                "min_price_tenge": None,
                "max_price_tenge": None,
                "max_pages": 1,
                "max_messages_per_run": 20,
                "location_keywords": None,
                "goal": "test",
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
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "db.sqlite3"
    return TelegramConfigController(
        token="dummy",
        chat_id=None,
        config_path=config_path,
        offset_path=tmp_path / "offset.txt",
        access_store=TelegramAccessStore(db_path),
        success_store=TelegramSuccessStore(db_path),
        project_root=tmp_path,
        allow_run_command=False,
    )


def _cfg(controller: TelegramConfigController) -> dict:
    with controller.config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────
# Basic wizard — button-based steps
# ──────────────────────────────────────────────

def test_city_step_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    text, _ = ctrl._handle_callback_data("wiz:set:city:almaty", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["city"] == "almaty"


def test_owner_step_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    text, _ = ctrl._handle_callback_data("wiz:set:owner:1", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["owner_type"] == 1


def test_categories_step_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    text, _ = ctrl._handle_callback_data("wiz:set:categories:prodazha", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["categories"] == ["prodazha"]


def test_rooms_step_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    text, _ = ctrl._handle_callback_data("wiz:set:rooms:2,3", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["rooms"] == [2, 3]


def test_min_price_manual_input_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    # open manual input state for min_price
    ctrl._handle_callback_data("wiz:manual:min_price", CHAT_ID, FROM_USER)
    text, _ = ctrl._handle_plain_text("15000000", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["min_price_tenge"] == 15_000_000


def test_max_price_manual_input_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    ctrl._handle_callback_data("wiz:manual:max_price", CHAT_ID, FROM_USER)
    text, _ = ctrl._handle_plain_text("60000000", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["max_price_tenge"] == 60_000_000


def test_max_pages_step_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    text, _ = ctrl._handle_callback_data("wiz:set:max_pages:3", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["max_pages"] == 3


def test_max_messages_step_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    text, _ = ctrl._handle_callback_data("wiz:set:max_messages:10", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["max_messages_per_run"] == 10


def test_location_keywords_step_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    text, _ = ctrl._handle_callback_data("wiz:set:location_keywords:kgd", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert "карагандинская область" in _cfg(ctrl)["location_keywords"]


def test_skip_optional_step_clears_value(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    # first set a value
    ctrl._handle_callback_data("wiz:set:max_price:50000000", CHAT_ID, FROM_USER)
    assert _cfg(ctrl)["max_price_tenge"] == 50_000_000
    # then skip → should clear to None
    text, _ = ctrl._handle_callback_data("wiz:skip:max_price", CHAT_ID, FROM_USER)
    assert "Пропущено" in text
    assert _cfg(ctrl)["max_price_tenge"] is None


# ──────────────────────────────────────────────
# Advanced wizard
# ──────────────────────────────────────────────

def test_floor_from_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    ctrl._handle_callback_data("advwiz:manual:floor_from", CHAT_ID, FROM_USER)
    text, _ = ctrl._handle_plain_text("3", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["floor_from"] == 3


def test_floor_to_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    ctrl._handle_callback_data("advwiz:manual:floor_to", CHAT_ID, FROM_USER)
    text, _ = ctrl._handle_plain_text("12", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["floor_to"] == 12


def test_not_first_floor_combo_both(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    text, _ = ctrl._handle_callback_data("advwiz:set:not_first_floor:both", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    cfg = _cfg(ctrl)
    assert cfg["not_first_floor"] is True
    assert cfg["not_last_floor"] is True


def test_not_first_floor_combo_none(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    text, _ = ctrl._handle_callback_data("advwiz:set:not_first_floor:none", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    cfg = _cfg(ctrl)
    assert cfg["not_first_floor"] is False
    assert cfg["not_last_floor"] is False


def test_area_from_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    ctrl._handle_callback_data("advwiz:manual:area_from", CHAT_ID, FROM_USER)
    text, _ = ctrl._handle_plain_text("45", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["area_from"] == 45.0


def test_year_built_from_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    ctrl._handle_callback_data("advwiz:manual:year_built_from", CHAT_ID, FROM_USER)
    text, _ = ctrl._handle_plain_text("2005", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["year_built_from"] == 2005


def test_text_search_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    ctrl._handle_callback_data("advwiz:manual:text_search", CHAT_ID, FROM_USER)
    text, _ = ctrl._handle_plain_text("кирпич", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["text_search"] == "кирпич"


# ──────────────────────────────────────────────
# Greeting / goal
# ──────────────────────────────────────────────

def test_goal_manual_input_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    ctrl._handle_callback_data("greet:manual", CHAT_ID, FROM_USER)
    text, _ = ctrl._handle_plain_text("Привет, интересует ваш объект!", CHAT_ID, FROM_USER)
    assert "Сохранено" in text
    assert _cfg(ctrl)["goal"] == "Привет, интересует ваш объект!"


def test_goal_preset_button_saved(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)
    # greet:set:base is the current callback for preset goal selection
    ok, msg = ctrl._apply_setting_value("goal", "base")
    assert ok
    assert "Сохранено" in msg
    assert "Интересует" in _cfg(ctrl)["goal"]


# ──────────────────────────────────────────────
# Full basic wizard flow (all 9 steps in sequence)
# ──────────────────────────────────────────────

def test_full_basic_wizard_persists_all_steps(tmp_path: Path) -> None:
    ctrl = _build(tmp_path)

    steps = [
        ("wiz:set:city:nur-sultan", "city", "nur-sultan"),
        ("wiz:set:owner:1", "owner_type", 1),
        ("wiz:set:categories:prodazha", "categories", ["prodazha"]),
        ("wiz:set:rooms:2,3", "rooms", [2, 3]),
        ("wiz:skip:min_price", "min_price_tenge", None),
        ("wiz:skip:max_price", "max_price_tenge", None),
        ("wiz:set:max_pages:2", "max_pages", 2),
        ("wiz:set:max_messages:15", "max_messages_per_run", 15),
        ("wiz:skip:location_keywords", "location_keywords", None),
    ]

    # Start wizard
    ctrl._handle_callback_data("wizard:start", CHAT_ID, FROM_USER)

    for callback, config_key, expected in steps:
        ctrl._handle_callback_data(callback, CHAT_ID, FROM_USER)
        assert _cfg(ctrl)[config_key] == expected, f"Step '{config_key}' not saved correctly"
