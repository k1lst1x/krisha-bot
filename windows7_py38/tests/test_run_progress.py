from __future__ import annotations

from pathlib import Path

from main import init_db, load_config, record_contact, was_contacted
from scraper import Listing


def _listing(listing_id: str = "100") -> Listing:
    return Listing(
        listing_id=listing_id,
        title="2-комнатная квартира",
        price="20 000 000 тг",
        district="Караганда",
        url=f"https://krisha.kz/a/show/{listing_id}",
        category="prodazha",
    )


def test_load_config_accepts_utf8_bom(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_bytes(b"\xef\xbb\xbf{\"city\": \"karaganda\"}")

    assert load_config(config_path) == {"city": "karaganda"}


def test_dry_run_contact_is_checkpoint_for_next_dry_run(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "contacts.db")
    try:
        record_contact(
            conn=conn,
            listing=_listing("101"),
            message="test",
            status="dry_run",
            response="not sent",
        )

        assert was_contacted(conn, "101", include_dry_run=True)
    finally:
        conn.close()


def test_dry_run_checkpoint_does_not_block_real_send(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "contacts.db")
    try:
        record_contact(
            conn=conn,
            listing=_listing("102"),
            message="test",
            status="dry_run",
            response="not sent",
        )

        assert not was_contacted(conn, "102", include_dry_run=False)
    finally:
        conn.close()


def test_failed_status_does_not_block_retry_in_send_mode(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "contacts.db")
    try:
        record_contact(
            conn=conn,
            listing=_listing("103"),
            message="test",
            status="failed",
            response="temporary error",
        )
        assert not was_contacted(conn, "103", include_dry_run=False)
    finally:
        conn.close()


def test_skipped_no_chat_blocks_retry_in_send_mode(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "contacts.db")
    try:
        record_contact(
            conn=conn,
            listing=_listing("104"),
            message="test",
            status="skipped_no_chat",
            response="Message button was not found on listing page.",
        )
        assert was_contacted(conn, "104", include_dry_run=False)
    finally:
        conn.close()


def test_record_contact_does_not_overwrite_sent_with_failed_retry(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "contacts.db")
    try:
        record_contact(
            conn=conn,
            listing=_listing("105"),
            message="sent message",
            status="sent",
            response="ok",
        )
        record_contact(
            conn=conn,
            listing=_listing("105"),
            message="failed retry",
            status="failed",
            response="temporary error",
        )

        row = conn.execute(
            "SELECT status, message, response FROM contacts WHERE listing_id = ?",
            ("105",),
        ).fetchone()

        assert row == ("sent", "sent message", "ok")
    finally:
        conn.close()
