from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from scraper import Listing


_PRICE_RE = re.compile(r"(\d[\d\s.,]*)")
_ROOMS_RE = re.compile(r"(\d+)\s*[- ]?\s*комн\w*", flags=re.IGNORECASE)
_AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*м", flags=re.IGNORECASE)
_FLOOR_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*эт", flags=re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def parse_price_tenge(raw_price: str) -> int | None:
    if not raw_price:
        return None

    text = raw_price.replace("\xa0", " ").lower()
    match = _PRICE_RE.search(text)
    if match is None:
        return None

    has_multiplier = any(unit in text for unit in ("млрд", "млн", "тыс"))
    normalized_number = _normalize_price_number(match.group(1), has_multiplier=has_multiplier)
    if not normalized_number:
        return None

    try:
        numeric = float(normalized_number)
    except ValueError:
        return None

    multiplier = 1
    if "млрд" in text:
        multiplier = 1_000_000_000
    elif "млн" in text:
        multiplier = 1_000_000
    elif "тыс" in text:
        multiplier = 1_000

    return int(numeric * multiplier)


def _normalize_price_number(raw_number: str, has_multiplier: bool) -> str:
    number = raw_number.replace(" ", "").strip(".,")
    if not number:
        return ""

    separator_count = number.count(".") + number.count(",")
    if separator_count == 0:
        return number

    parts = re.split(r"[.,]", number)
    if len(parts) == 2:
        left, right = parts
        if not left or not right:
            return ""
        if not has_multiplier and len(right) == 3 and len(left) <= 3:
            return f"{left}{right}"
        return f"{left}.{right}"

    if parts and all(part.isdigit() for part in parts):
        if len(parts[0]) <= 3 and all(len(part) == 3 for part in parts[1:]):
            return "".join(parts)

        integer = "".join(parts[:-1])
        fraction = parts[-1]
        if integer and fraction:
            return f"{integer}.{fraction}"

    return number


def parse_rooms_count(*texts: str) -> int | None:
    for text in texts:
        if not text:
            continue
        match = _ROOMS_RE.search(text.lower())
        if match is None:
            continue
        try:
            return int(match.group(1))
        except ValueError:
            continue
    return None


def parse_area_m2(*texts: str) -> float | None:
    for text in texts:
        if not text:
            continue
        match = _AREA_RE.search(text)
        if match is None:
            continue
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            continue
    return None


def parse_floor(*texts: str) -> tuple[int, int] | None:
    """Return (floor, total_floors) or None."""
    for text in texts:
        if not text:
            continue
        match = _FLOOR_RE.search(text)
        if match:
            try:
                return int(match.group(1)), int(match.group(2))
            except ValueError:
                continue
    return None


def parse_year_built(*texts: str) -> int | None:
    for text in texts:
        if not text:
            continue
        match = _YEAR_RE.search(text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


@dataclass(frozen=True)
class ListingFilters:
    min_price_tenge: int | None = None
    max_price_tenge: int | None = None
    rooms: set[int] | None = None
    location_keywords: list[str] | None = None
    floor_from: int | None = None
    floor_to: int | None = None
    not_first_floor: bool = False
    not_last_floor: bool = False
    area_from: float | None = None
    area_to: float | None = None
    year_built_from: int | None = None
    year_built_to: int | None = None
    text_search: str | None = None

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ListingFilters":
        rooms_value = config.get("rooms")
        parsed_rooms: set[int] | None = None

        if isinstance(rooms_value, list):
            candidate_rooms = {
                parsed
                for value in rooms_value
                if (parsed := cls._parse_int(value)) is not None
            }
            if candidate_rooms:
                parsed_rooms = candidate_rooms
        elif isinstance(rooms_value, str):
            candidate_rooms = {
                int(chunk.strip())
                for chunk in rooms_value.split(",")
                if chunk.strip().isdigit()
            }
            if candidate_rooms:
                parsed_rooms = candidate_rooms

        keywords_value = config.get("location_keywords")
        parsed_keywords: list[str] | None = None
        if isinstance(keywords_value, list):
            cleaned = [str(item).strip().lower() for item in keywords_value if str(item).strip()]
            if cleaned:
                parsed_keywords = cleaned
        elif isinstance(keywords_value, str):
            cleaned = [part.strip().lower() for part in keywords_value.split(",") if part.strip()]
            if cleaned:
                parsed_keywords = cleaned

        min_price = cls._parse_int(config.get("min_price_tenge"))
        max_price = cls._parse_int(config.get("max_price_tenge"))

        text_raw = str(config.get("text_search") or "").strip()

        return cls(
            min_price_tenge=min_price,
            max_price_tenge=max_price,
            rooms=parsed_rooms,
            location_keywords=parsed_keywords,
            floor_from=cls._parse_int(config.get("floor_from")),
            floor_to=cls._parse_int(config.get("floor_to")),
            not_first_floor=bool(config.get("not_first_floor")),
            not_last_floor=bool(config.get("not_last_floor")),
            area_from=cls._parse_float(config.get("area_from")),
            area_to=cls._parse_float(config.get("area_to")),
            year_built_from=cls._parse_int(config.get("year_built_from")),
            year_built_to=cls._parse_int(config.get("year_built_to")),
            text_search=text_raw or None,
        )

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(str(value).strip())
        except ValueError:
            return None

    @staticmethod
    def _parse_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).strip().replace(",", "."))
        except ValueError:
            return None

    def accepts(self, listing: Listing) -> tuple[bool, str]:
        price_tenge = parse_price_tenge(listing.price)
        if self.min_price_tenge is not None:
            if price_tenge is None:
                return False, "price_missing"
            if price_tenge < self.min_price_tenge:
                return False, "price_below_min"

        if self.max_price_tenge is not None:
            if price_tenge is None:
                return False, "price_missing"
            if price_tenge > self.max_price_tenge:
                return False, "price_above_max"

        if self.rooms:
            rooms_count = parse_rooms_count(listing.title, listing.description)
            if rooms_count is None:
                return False, "rooms_missing"
            if rooms_count not in self.rooms:
                return False, f"rooms_not_allowed:{rooms_count}"

        if self.location_keywords:
            haystack = " ".join([listing.title, listing.district, listing.description]).lower()
            if not any(keyword in haystack for keyword in self.location_keywords):
                return False, "location_not_matched"

        if self.text_search:
            haystack = " ".join([listing.title, listing.district, listing.description]).lower()
            if self.text_search.lower() not in haystack:
                return False, "text_search_not_matched"

        floor_info = parse_floor(listing.title, listing.district, listing.description)
        if floor_info is not None:
            floor, total_floors = floor_info
            if self.floor_from is not None and floor < self.floor_from:
                return False, f"floor_below_min:{floor}"
            if self.floor_to is not None and floor > self.floor_to:
                return False, f"floor_above_max:{floor}"
            if self.not_first_floor and floor == 1:
                return False, "first_floor_excluded"
            if self.not_last_floor and floor == total_floors:
                return False, "last_floor_excluded"

        if self.area_from is not None or self.area_to is not None:
            area = parse_area_m2(listing.title, listing.description)
            if area is not None:
                if self.area_from is not None and area < self.area_from:
                    return False, f"area_below_min:{area}"
                if self.area_to is not None and area > self.area_to:
                    return False, f"area_above_max:{area}"

        if self.year_built_from is not None or self.year_built_to is not None:
            year = parse_year_built(listing.title, listing.description)
            if year is not None:
                if self.year_built_from is not None and year < self.year_built_from:
                    return False, f"year_below_min:{year}"
                if self.year_built_to is not None and year > self.year_built_to:
                    return False, f"year_above_max:{year}"

        return True, "ok"
