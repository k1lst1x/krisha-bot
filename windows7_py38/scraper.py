from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup, Tag


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Listing:
    listing_id: str
    title: str
    price: str
    district: str
    url: str
    category: str
    owner_name: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class KrishaScraper:
    BASE_URL = "https://krisha.kz"

    CATEGORY_PATHS = {
        "arenda": "/arenda/kvartiry/{city}/",
        "prodazha": "/prodazha/kvartiry/{city}/",
        "kommercheskaya": "/prodazha/kommercheskaya-nedvizhimost/{city}/",
    }

    def __init__(
        self,
        city: str,
        owner_type: int | None = 1,
        request_delay_sec: float = 1.5,
        timeout_sec: int = 20,
        extra_params: dict[str, str | int | float] | None = None,
    ) -> None:
        self.city = city.strip().strip("/")
        self.owner_type = owner_type
        self.request_delay_sec = request_delay_sec
        self.timeout_sec = timeout_sec
        # Additional URL parameters passed straight to the krisha.kz API
        # (e.g. das[live.floor][from], das[house.year][from], text, …).
        self.extra_params: dict[str, str | int | float] = extra_params or {}
        self.session = requests.Session()
        retry = Retry(
            total=4,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.6",
            }
        )

    def iter_listings(
        self,
        category: str,
        max_pages: int = 1,
        page_stop_below: int = 20,
        fetch_details: bool = False,
    ) -> Iterable[Listing]:
        for page in range(1, max_pages + 1):
            html = self.fetch_listing_page(category=category, page=page)
            listings = self.parse_listing_page(html=html, category=category)
            LOGGER.info("Parsed %s listings from %s page %s", len(listings), category, page)

            for listing in listings:
                if fetch_details:
                    yield self.enrich_listing(listing)
                else:
                    yield listing

            if len(listings) < page_stop_below:
                LOGGER.info(
                    "Stopping pagination for %s: page returned %s listings",
                    category,
                    len(listings),
                )
                break

    def fetch_listing_page(self, category: str, page: int = 1) -> str:
        url = self.build_category_url(category)
        params = self._listing_page_params(page=page)

        response = self.session.get(url, params=params, timeout=self.timeout_sec)
        response.raise_for_status()
        time.sleep(self.request_delay_sec)
        return response.text

    def _listing_page_params(self, page: int = 1) -> dict[str, str | int | float]:
        params: dict[str, str | int | float] = {}
        if self.owner_type == 1:
            params["das[who]"] = 1
        elif self.owner_type == 2:
            params["das[_sys.fromAgent]"] = 1
        elif self.owner_type is not None:
            params["das[who]"] = self.owner_type
        if page > 1:
            params["page"] = page
        params.update(self.extra_params)
        return params

    @classmethod
    def extra_params_from_config(cls, config: dict) -> dict[str, str | int | float]:
        """Build extra URL params from config keys that map to krisha.kz das[] params."""
        p: dict[str, str | int | float] = {}

        def _int(key: str) -> int | None:
            try:
                return int(config[key])
            except (KeyError, TypeError, ValueError):
                return None

        def _float(key: str) -> float | None:
            try:
                return float(str(config[key]).replace(",", "."))
            except (KeyError, TypeError, ValueError):
                return None

        if (v := _int("floor_from")) is not None:
            p["das[live.floor][from]"] = v
        if (v := _int("floor_to")) is not None:
            p["das[live.floor][to]"] = v
        if config.get("not_first_floor"):
            p["das[_sys.notFirstFloor]"] = 1
        if config.get("not_last_floor"):
            p["das[_sys.notLastFloor]"] = 1
        if (v := _int("building_floors_from")) is not None:
            p["das[house.floors][from]"] = v
        if (v := _int("building_floors_to")) is not None:
            p["das[house.floors][to]"] = v
        if (v := _float("area_from")) is not None:
            p["das[live.square][from]"] = v
        if (v := _float("area_to")) is not None:
            p["das[live.square][to]"] = v
        if (v := _float("kitchen_area_from")) is not None:
            p["das[kitchen.square][from]"] = v
        if (v := _float("kitchen_area_to")) is not None:
            p["das[kitchen.square][to]"] = v
        if (v := _int("year_built_from")) is not None:
            p["das[house.year][from]"] = v
        if (v := _int("year_built_to")) is not None:
            p["das[house.year][to]"] = v
        if (v := _int("min_price_tenge")) is not None:
            p["das[price][from]"] = v
        if (v := _int("max_price_tenge")) is not None:
            p["das[price][to]"] = v
        if text := str(config.get("text_search") or "").strip():
            p["text"] = text
        return p

    def build_category_url(self, category: str) -> str:
        try:
            path = self.CATEGORY_PATHS[category]
        except KeyError as exc:
            known = ", ".join(sorted(self.CATEGORY_PATHS))
            raise ValueError(f"Unknown category {category!r}. Known: {known}") from exc
        return urljoin(self.BASE_URL, path.format(city=self.city))

    def parse_listing_page(self, html: str, category: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        listings: list[Listing] = []
        seen: set[str] = set()

        cards = self._find_listing_cards(soup)
        for card in cards:
            listing = self._parse_card(card=card, category=category)
            if not listing or listing.listing_id in seen:
                continue
            seen.add(listing.listing_id)
            listings.append(listing)

        if not listings:
            # JSON-LD fallback: krisha.kz may embed Schema.org structured data.
            for listing in self._parse_jsonld_listings(soup, category):
                if listing.listing_id not in seen:
                    seen.add(listing.listing_id)
                    listings.append(listing)

        return listings

    def enrich_listing(self, listing: Listing) -> Listing:
        response = self.session.get(listing.url, timeout=self.timeout_sec)
        response.raise_for_status()
        time.sleep(self.request_delay_sec)

        soup = BeautifulSoup(response.text, "lxml")
        description = self._first_text(
            soup,
            [
                ".offer__description",
                "[data-name='description']",
                ".a-text.a-text-white-spaces",
                "[class*='description']",
            ],
        )
        owner_name = self._first_text(
            soup,
            [
                ".owners__name",
                ".offer__advert-title",
                "[class*='owner'] [class*='name']",
            ],
        )

        return Listing(
            listing_id=listing.listing_id,
            title=listing.title,
            price=listing.price,
            district=listing.district,
            url=listing.url,
            category=listing.category,
            owner_name=owner_name or listing.owner_name,
            description=description,
        )

    def _find_listing_cards(self, soup: BeautifulSoup) -> list[Tag]:
        # Level 1: known CSS class/attribute patterns.
        cards = soup.select(".a-card[data-id], .a-card, article[data-id], [data-id]")
        if cards:
            return [card for card in cards if isinstance(card, Tag)]

        # Level 2: structural — collect distinct parent containers of listing links.
        links = soup.select("a[href*='/a/show/']")
        seen_parents: set[int] = set()
        parents: list[Tag] = []
        for link in links:
            parent = link.parent
            if not isinstance(parent, Tag):
                continue
            pid = id(parent)
            if pid not in seen_parents:
                seen_parents.add(pid)
                parents.append(parent)
        return parents

    def _parse_jsonld_listings(self, soup: BeautifulSoup, category: str) -> list[Listing]:
        """Extract listings from Schema.org JSON-LD — stable even after HTML rewrites."""
        results: list[Listing] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            for item in self._jsonld_listing_items(data):
                url_raw = str(item.get("url") or "").strip()
                if not url_raw:
                    continue
                url = urljoin(self.BASE_URL, url_raw)
                listing_id_match = re.search(r"/a/show/(\d+)", url)
                if not listing_id_match:
                    continue
                listing_id = listing_id_match.group(1)
                name = str(item.get("name") or "").strip()
                offers = item.get("offers", {}) or {}
                if isinstance(offers, list):
                    price_spec = next((offer for offer in offers if isinstance(offer, dict)), {})
                elif isinstance(offers, dict):
                    price_spec = offers
                else:
                    price_spec = {}
                price_val = str(price_spec.get("price") or "").strip()
                price_currency = str(price_spec.get("priceCurrency") or "").strip()
                price = f"{price_val} {price_currency}".strip() if price_val else ""
                address_raw = item.get("address", {}) or {}
                address = address_raw if isinstance(address_raw, dict) else {}
                district = str(address.get("addressLocality") or address.get("streetAddress") or "").strip()
                results.append(
                    Listing(
                        listing_id=listing_id,
                        title=name,
                        price=price,
                        district=district,
                        url=url,
                        category=category,
                    )
                )
        return results

    def _jsonld_listing_items(self, data: object) -> list[dict]:
        if isinstance(data, list):
            items: list[dict] = []
            for entry in data:
                items.extend(self._jsonld_listing_items(entry))
            return items

        if not isinstance(data, dict):
            return []

        graph = data.get("@graph")
        if isinstance(graph, list):
            return self._jsonld_listing_items(graph)

        raw_type = data.get("@type")
        types = set(raw_type) if isinstance(raw_type, list) else {raw_type}
        if types.intersection({"ItemList", "SearchResultsPage"}):
            items = []
            for entry in data.get("itemListElement", []):
                if isinstance(entry, str):
                    items.append({"url": entry})
                    continue
                if not isinstance(entry, dict):
                    continue
                item = entry.get("item") or entry
                if isinstance(item, str):
                    items.append({"url": item})
                else:
                    items.extend(self._jsonld_listing_items(item))
            return items

        if types.intersection({"Apartment", "ApartmentComplex", "RealEstateListing"}) or data.get("url"):
            return [data]

        return []

    def _parse_card(self, card: Tag, category: str) -> Listing | None:
        url = self._extract_url(card)
        listing_id = self._extract_id(card, url)
        if not listing_id or not url:
            return None

        title = self._first_text(
            card,
            [
                ".a-card__title",
                "[data-name='title']",
                "a[href*='/a/show/']",
                "[class*='title']",
            ],
        )
        price = self._first_text(
            card,
            [
                ".a-card__price",
                "[data-name='price']",
                "[class*='price']",
            ],
        )
        district = self._first_text(
            card,
            [
                ".a-card__subtitle",
                ".a-card__address",
                "[data-name='subtitle']",
                "[class*='address']",
                "[class*='subtitle']",
            ],
        )
        owner_name = self._first_text(
            card,
            [
                ".owners__name",
                "[class*='owner']",
            ],
        )

        # Structural fallback: if CSS selectors found nothing, derive from DOM position.
        if not title:
            title = self._structural_title(card)
        if not price:
            price = self._structural_price(card)

        return Listing(
            listing_id=listing_id,
            title=title,
            price=price,
            district=district,
            url=url,
            category=category,
            owner_name=owner_name,
        )

    def _structural_title(self, card: Tag) -> str:
        """Derive title heuristically: text of the first listing link."""
        link = card.select_one("a[href*='/a/show/']")
        if link:
            text = link.get_text(" ", strip=True)
            if text:
                return re.sub(r"\s+", " ", text)
        return ""

    def _structural_price(self, card: Tag) -> str:
        """Derive price heuristically: first element whose text contains a number + тг/₸."""
        price_re = re.compile(r"\d[\d\s]*(?:тг|₸|tg)", re.IGNORECASE)
        for el in card.find_all(True):
            if not isinstance(el, Tag):
                continue
            text = el.get_text(" ", strip=True)
            if price_re.search(text) and len(text) < 80:
                return re.sub(r"\s+", " ", text)
        return ""

    def _extract_url(self, card: Tag) -> str:
        link = card.select_one("a[href*='/a/show/']")
        if not isinstance(link, Tag):
            return ""

        href = link.get("href")
        if not isinstance(href, str):
            return ""
        return urljoin(self.BASE_URL, href)

    def _extract_id(self, card: Tag, url: str) -> str:
        for attr in ("data-id", "data-item-id", "id"):
            value = card.get(attr)
            if isinstance(value, str) and value.strip():
                match = re.search(r"\d+", value)
                if match:
                    return match.group(0)

        match = re.search(r"/a/show/(\d+)", url)
        if match:
            return match.group(1)
        return ""

    def _first_text(self, root: Tag | BeautifulSoup, selectors: list[str]) -> str:
        for selector in selectors:
            node = root.select_one(selector)
            if node:
                text = node.get_text(" ", strip=True)
                if text:
                    return re.sub(r"\s+", " ", text)
        return ""
