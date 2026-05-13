from __future__ import annotations

from listing_filters import ListingFilters, parse_price_tenge, parse_rooms_count
from scraper import Listing


def test_parse_price_tenge_handles_plain_number() -> None:
    assert parse_price_tenge("24 300 000 〒") == 24_300_000


def test_parse_price_tenge_handles_million_suffix() -> None:
    assert parse_price_tenge("52.5 млн 〒") == 52_500_000


def test_parse_price_tenge_handles_dot_thousands_without_suffix() -> None:
    assert parse_price_tenge("24.300.000 ₸") == 24_300_000


def test_parse_rooms_count_extracts_from_title() -> None:
    assert parse_rooms_count("3-комнатная квартира") == 3


def test_listing_filters_from_config_ignores_invalid_room_list_entries() -> None:
    filters = ListingFilters.from_config({"rooms": ["2", "bad", "", 3]})

    assert filters.rooms == {2, 3}


def test_listing_filters_rejects_by_price_and_rooms() -> None:
    filters = ListingFilters(min_price_tenge=None, max_price_tenge=50_000_000, rooms={2, 3})
    listing = Listing(
        listing_id="123",
        title="4-комнатная квартира",
        price="55 млн 〒",
        district="Караганда",
        url="https://krisha.kz/a/show/123",
        category="prodazha",
    )

    accepted, reason = filters.accepts(listing)

    assert accepted is False
    assert reason == "price_above_max"


def test_listing_filters_accepts_matching_listing() -> None:
    filters = ListingFilters(
        min_price_tenge=None,
        max_price_tenge=50_000_000,
        rooms={2, 3},
        location_keywords=["карагандинская область", "караганда"],
    )
    listing = Listing(
        listing_id="456",
        title="2-комнатная квартира",
        price="24.3 млн 〒",
        district="Карагандинская область, Темиртау",
        url="https://krisha.kz/a/show/456",
        category="prodazha",
    )

    accepted, reason = filters.accepts(listing)

    assert accepted is True
    assert reason == "ok"
