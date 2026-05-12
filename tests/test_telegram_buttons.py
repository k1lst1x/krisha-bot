import json
from pathlib import Path

from telegram_control import TelegramAccessStore, TelegramConfigController, TelegramSuccessStore


def _build_controller(tmp_path: Path) -> TelegramConfigController:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "city": "karagandinskaja-oblast",
                "owner_type": 1,
                "categories": ["prodazha"],
                "rooms": [2, 3],
                "min_price_tenge": None,
                "max_price_tenge": 50000000,
                "location_keywords": None,
                "max_pages": 1,
                "max_messages_per_run": 20,
                "goal": "x",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "db.sqlite3"
    access_store = TelegramAccessStore(db_path)
    success_store = TelegramSuccessStore(db_path)
    return TelegramConfigController(
        token="dummy",
        chat_id=None,
        config_path=config_path,
        offset_path=tmp_path / "offset.txt",
        access_store=access_store,
        success_store=success_store,
        project_root=tmp_path,
        allow_run_command=False,
    )


def test_apply_button_value_goal_and_location(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)

    goal_result = controller._apply_button_value("val:goal:base")
    location_result = controller._apply_button_value("val:location_keywords:kgd")

    with controller.config_path.open("r", encoding="utf-8") as handle:
        cfg = json.load(handle)

    assert "Сохранено" in goal_result
    assert "Сохранено" in location_result
    assert cfg["goal"] == "Интересует ваш объект, хотим обсудить условия"
    assert cfg["location_keywords"] == ["карагандинская область", "караганда"]


def test_search_wizard_moves_to_next_step(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)
    from_user = {"id": 77}
    chat_id = "123"

    start_text, start_keyboard = controller._handle_callback_data(
        data="wizard:start",
        chat_id=chat_id,
        from_user=from_user,
    )
    next_text, _ = controller._handle_callback_data(
        data="wiz:set:city:karaganda",
        chat_id=chat_id,
        from_user=from_user,
    )

    with controller.config_path.open("r", encoding="utf-8") as handle:
        cfg = json.load(handle)

    assert "шаг 1/9" in start_text.lower()
    assert start_keyboard is not None
    assert "шаг 2/9" in next_text.lower()
    assert cfg["city"] == "karaganda"


def test_wizard_skip_clears_optional_filter_value(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)
    from_user = {"id": 77}
    chat_id = "123"

    result_text, _ = controller._handle_callback_data(
        data="wiz:skip:max_price",
        chat_id=chat_id,
        from_user=from_user,
    )

    with controller.config_path.open("r", encoding="utf-8") as handle:
        cfg = json.load(handle)

    assert "Пропущено" in result_text
    assert cfg["max_price_tenge"] is None


def test_required_wizard_steps_do_not_have_skip_button(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)

    for step in ("city", "categories"):
        _, keyboard = controller._wizard_step_view(step)
        callbacks = {
            button["callback_data"]
            for row in keyboard["inline_keyboard"]
            for button in row
            if "callback_data" in button
        }
        assert f"wiz:skip:{step}" not in callbacks


def test_advanced_wizard_exposes_building_and_kitchen_filters(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)

    for step in ("building_floors_from", "building_floors_to", "kitchen_area_from", "kitchen_area_to"):
        _, keyboard = controller._wizard_step_view(step)
        callbacks = {
            button["callback_data"]
            for row in keyboard["inline_keyboard"]
            for button in row
            if "callback_data" in button
        }
        assert f"advwiz:manual:{step}" in callbacks


def test_greeting_manual_input_flow(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)
    from_user = {"id": 88}
    chat_id = "456"

    prompt_text, prompt_keyboard = controller._handle_callback_data(
        data="greet:manual",
        chat_id=chat_id,
        from_user=from_user,
    )
    result_text, result_keyboard = controller._handle_plain_text(
        text="Ищем квартиру, готовы быстро обсудить условия",
        chat_id=chat_id,
        from_user=from_user,
    )

    with controller.config_path.open("r", encoding="utf-8") as handle:
        cfg = json.load(handle)

    assert "Отправь текст приветственного сообщения" in prompt_text
    assert prompt_keyboard is None
    assert "Сохранено" in result_text
    assert result_keyboard is not None
    assert cfg["goal"] == "Ищем квартиру, готовы быстро обсудить условия"


def test_wizard_owner_step_has_manual_input_button(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)

    _, keyboard = controller._wizard_step_view("owner")
    callbacks = {
        button["callback_data"]
        for row in keyboard["inline_keyboard"]
        for button in row
        if "callback_data" in button
    }

    assert "wiz:manual:owner" in callbacks


def test_wizard_price_steps_have_manual_input_buttons(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)

    for step in ("min_price", "max_price"):
        _, keyboard = controller._wizard_step_view(step)
        callbacks = {
            button["callback_data"]
            for row in keyboard["inline_keyboard"]
            for button in row
            if "callback_data" in button
        }

        assert f"wiz:manual:{step}" in callbacks
        assert ["Ввести вручную"] in [
            [button["text"] for button in row]
            for row in keyboard["inline_keyboard"]
        ]


def test_run_starts_in_background_and_reports_status(tmp_path: Path, monkeypatch) -> None:
    controller = _build_controller(tmp_path)
    sent_messages: list[tuple[str, str]] = []

    class FakePopen:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 0

        def wait(self, timeout=None):  # noqa: ANN001
            return 0

        def kill(self) -> None:
            self.returncode = -1

    monkeypatch.setattr("telegram_control.subprocess.Popen", FakePopen)
    monkeypatch.setattr(
        controller,
        "_send_message",
        lambda chat_id, text, reply_markup=None: sent_messages.append((chat_id, text)) or 321,
    )

    start_text = controller._run_krisha_process(limit=5, chat_id="123")
    status_text = controller._run_status_text()

    assert start_text == ""
    assert sent_messages
    assert "Ищу объявления" in sent_messages[0][1]
    assert "Поиск сейчас выполняется" in status_text


def test_run_menu_has_send_buttons(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)
    keyboard = controller._run_menu_keyboard()
    callbacks = {
        button["callback_data"]
        for row in keyboard["inline_keyboard"]
        for button in row
        if "callback_data" in button
    }
    assert "run:send:5" in callbacks
    assert "run:send:10" in callbacks
    assert "run:send:20" in callbacks


def test_run_command_send_mode_uses_send_flag(tmp_path: Path, monkeypatch) -> None:
    controller = _build_controller(tmp_path)

    class FakePopen:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 0

        def wait(self, timeout=None):  # noqa: ANN001
            return 0

        def kill(self) -> None:
            self.returncode = -1

    monkeypatch.setattr("telegram_control.subprocess.Popen", FakePopen)
    monkeypatch.setattr(controller, "_send_message", lambda chat_id, text, reply_markup=None: 321)
    controller.allow_run_command = True

    response = controller._run_search(args="krisha send 5", chat_id="123")
    assert response == ""
    assert controller._active_run is not None
    command = controller._active_run.args[0]
    assert "--send" in command
    assert "--dry-run" not in command


def test_run_progress_message_is_deleted_on_completion(tmp_path: Path, monkeypatch) -> None:
    controller = _build_controller(tmp_path)
    deleted_messages: list[tuple[str, int]] = []

    class FakePopen:
        def __init__(self, *args, **kwargs) -> None:
            self.returncode = None

        def poll(self):
            return self.returncode

    fake_processes: list[FakePopen] = []

    def fake_popen(*args, **kwargs):  # noqa: ANN001
        process = FakePopen(*args, **kwargs)
        fake_processes.append(process)
        return process

    monkeypatch.setattr("telegram_control.subprocess.Popen", fake_popen)
    monkeypatch.setattr(controller, "_send_message", lambda chat_id, text, reply_markup=None: 222)
    monkeypatch.setattr(
        controller,
        "_delete_message",
        lambda chat_id, message_id: deleted_messages.append((chat_id, message_id)),
    )

    controller._run_krisha_process(limit=5, chat_id="123")
    fake_processes[0].returncode = 0
    controller._poll_active_run()

    assert deleted_messages == [("123", 222)]


def test_run_poll_sends_result_notification_once(tmp_path: Path, monkeypatch) -> None:
    controller = _build_controller(tmp_path)
    sent_messages: list[tuple[str, str, dict | None]] = []

    class FakePopen:
        def __init__(self, *args, **kwargs) -> None:
            self.returncode = None

        def poll(self):
            return self.returncode

    fake_processes: list[FakePopen] = []

    def fake_popen(*args, **kwargs):  # noqa: ANN001
        process = FakePopen(*args, **kwargs)
        fake_processes.append(process)
        return process

    monkeypatch.setattr("telegram_control.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        controller,
        "_send_message",
        lambda chat_id, text, reply_markup=None: sent_messages.append((chat_id, text, reply_markup)) or 111,
    )
    monkeypatch.setattr(controller, "_edit_message_text", lambda chat_id, message_id, text: None)

    controller._run_krisha_process(limit=5, chat_id="123")
    assert controller._active_run_log_path is not None

    with controller._active_run_log_path.open("a", encoding="utf-8") as log_handle:
        log_handle.write(
            '2026-04-30 00:00:00,000 INFO krisha-bot: RESULT '
            '{"listing_id":"555","status":"dry_run","district":"Алатау","price":"30 000 000","url":"https://krisha.kz/a/show/555","chat_url":"","message":"Привет"}\n'
        )

    controller._poll_active_run()
    fake_processes[0].returncode = 0
    controller._poll_active_run()

    digest_messages = [item for item in sent_messages if item[1].startswith("✅ Проверено (dry-run)")]
    assert len(digest_messages) == 1
    assert "#555" in digest_messages[0][1]
    assert digest_messages[0][2] is not None


def test_legacy_callback_data_is_redirected_to_main_menu(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)
    from_user = {"id": 99}

    text, keyboard = controller._handle_callback_data(
        data="val:city:karaganda",
        chat_id="777",
        from_user=from_user,
    )

    assert "старая кнопка" in text.lower()
    assert keyboard is not None


def test_wizard_manual_input_has_return_button(tmp_path: Path) -> None:
    controller = _build_controller(tmp_path)
    from_user = {"id": 100}
    chat_id = "888"

    text, keyboard = controller._handle_callback_data(
        data="wiz:manual:owner",
        chat_id=chat_id,
        from_user=from_user,
    )

    assert "нажми /cancel" in text.lower()
    assert keyboard is not None
    callbacks = {
        button["callback_data"]
        for row in keyboard["inline_keyboard"]
        for button in row
        if "callback_data" in button
    }
    assert "wiz:return:owner" in callbacks


def test_sync_once_continues_when_update_handler_raises(tmp_path: Path, monkeypatch) -> None:
    controller = _build_controller(tmp_path)
    updates = [
        {
            "update_id": 41,
            "callback_query": {
                "id": "cbq-1",
                "data": "menu:main",
                "from": {"id": 77},
                "message": {"chat": {"id": "123"}},
            },
        }
    ]

    monkeypatch.setattr(controller, "_get_updates", lambda offset: updates)
    monkeypatch.setattr(
        controller,
        "_handle_callback_query",
        lambda payload: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    processed = controller.sync_once()

    assert processed == 0
    assert controller.offset_path.read_text(encoding="utf-8").strip() == "42"


def test_menu_command_sends_main_menu_keyboard(tmp_path: Path, monkeypatch) -> None:
    controller = _build_controller(tmp_path)
    sent: list[tuple[str, str, dict | None]] = []

    monkeypatch.setattr(
        controller,
        "_send_message",
        lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)) or 1,
    )

    response = controller._handle_command("/menu", chat_id="123", from_user={"id": 1})

    assert response == ""
    assert sent
    chat_id, text, markup = sent[0]
    assert chat_id == "123"
    assert markup is not None
    all_callbacks = {
        btn["callback_data"]
        for row in markup["inline_keyboard"]
        for btn in row
        if "callback_data" in btn
    }
    assert "menu:run" in all_callbacks
    assert "menu:settings" in all_callbacks
