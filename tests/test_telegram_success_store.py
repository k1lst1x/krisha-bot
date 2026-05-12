from pathlib import Path

from telegram_control import TelegramSuccessStore


def test_success_store_add_and_list(tmp_path: Path) -> None:
    db_path = tmp_path / "success_store.db"
    store = TelegramSuccessStore(db_path)

    first_id = store.add_success(
        platform="krisha",
        listing_url="https://krisha.kz/a/show/1",
        chat_link="https://t.me/c/1/2",
        note="ok",
        created_by_user_id=10,
        created_by_chat_id="20",
    )
    second_id = store.add_success(
        platform="hh",
        listing_url="https://hh.kz/vacancy/2",
        chat_link="https://t.me/c/1/3",
        note="follow up",
        created_by_user_id=11,
        created_by_chat_id="21",
    )

    rows = store.list_recent(limit=10)

    assert first_id > 0
    assert second_id > first_id
    assert len(rows) == 2
    assert rows[0]["id"] == second_id
    assert rows[0]["platform"] == "hh"
    assert rows[1]["id"] == first_id
