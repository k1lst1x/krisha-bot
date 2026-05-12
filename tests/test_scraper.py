from scraper import KrishaScraper


HTML = """
<html>
  <body>
    <div class="a-card" data-id="123456">
      <a class="a-card__title" href="/a/show/123456">2-комнатная квартира</a>
      <div class="a-card__price">250 000 тг.</div>
      <div class="a-card__subtitle">Караганда, Казыбек би р-н</div>
    </div>
    <div class="a-card">
      <a class="a-card__title" href="/a/show/654321">1-комнатная квартира</a>
      <div class="a-card__price">180 000 тг.</div>
      <div class="a-card__address">Караганда, Юго-Восток</div>
    </div>
  </body>
</html>
"""


def test_parse_listing_page_extracts_cards() -> None:
    scraper = KrishaScraper(city="karaganda", request_delay_sec=0)

    listings = scraper.parse_listing_page(HTML, category="arenda")

    assert len(listings) == 2
    assert listings[0].listing_id == "123456"
    assert listings[0].title == "2-комнатная квартира"
    assert listings[0].price == "250 000 тг."
    assert listings[0].district == "Караганда, Казыбек би р-н"
    assert listings[0].url == "https://krisha.kz/a/show/123456"
    assert listings[1].listing_id == "654321"


def test_listing_page_params_match_krisha_owner_filters() -> None:
    owner_scraper = KrishaScraper(city="karaganda", owner_type=1, request_delay_sec=0)
    agent_scraper = KrishaScraper(city="karaganda", owner_type=2, request_delay_sec=0)
    all_scraper = KrishaScraper(city="karaganda", owner_type=None, request_delay_sec=0)

    assert owner_scraper._listing_page_params(page=2) == {"das[who]": 1, "page": 2}
    assert agent_scraper._listing_page_params() == {"das[_sys.fromAgent]": 1}
    assert all_scraper._listing_page_params() == {}


def test_extra_params_from_config_maps_advanced_filters() -> None:
    params = KrishaScraper.extra_params_from_config(
        {
            "floor_from": 2,
            "floor_to": 9,
            "building_floors_from": 5,
            "building_floors_to": 16,
            "area_from": 45,
            "area_to": 90,
            "kitchen_area_from": 8,
            "kitchen_area_to": 15,
            "year_built_from": 2000,
            "year_built_to": 2020,
            "text_search": "ремонт",
            "not_first_floor": True,
            "not_last_floor": True,
        }
    )

    assert params["das[live.floor][from]"] == 2
    assert params["das[live.floor][to]"] == 9
    assert params["das[house.floors][from]"] == 5
    assert params["das[house.floors][to]"] == 16
    assert params["das[live.square][from]"] == 45.0
    assert params["das[live.square][to]"] == 90.0
    assert params["das[kitchen.square][from]"] == 8.0
    assert params["das[kitchen.square][to]"] == 15.0
    assert params["das[house.year][from]"] == 2000
    assert params["das[house.year][to]"] == 2020
    assert params["das[_sys.notFirstFloor]"] == 1
    assert params["das[_sys.notLastFloor]"] == 1
    assert params["text"] == "ремонт"


def test_parse_jsonld_itemlist_with_string_item_urls() -> None:
    html = """
    <html>
      <body>
        <script type="application/ld+json">
        {
          "@type": "ItemList",
          "itemListElement": [
            {"@type": "ListItem", "item": "https://krisha.kz/a/show/777888"}
          ]
        }
        </script>
      </body>
    </html>
    """
    scraper = KrishaScraper(city="karaganda", request_delay_sec=0)

    listings = scraper.parse_listing_page(html, category="prodazha")

    assert len(listings) == 1
    assert listings[0].listing_id == "777888"
    assert listings[0].url == "https://krisha.kz/a/show/777888"


def test_parse_jsonld_array_itemlist_with_offer_list() -> None:
    html = """
    <html>
      <body>
        <script type="application/ld+json">
        [
          {
            "@type": "ItemList",
            "itemListElement": [
              {
                "@type": "ListItem",
                "item": {
                  "@type": ["Apartment", "Product"],
                  "url": "/a/show/888999",
                  "name": "3-комнатная квартира",
                  "offers": [
                    {"price": "42000000", "priceCurrency": "KZT"}
                  ],
                  "address": {"addressLocality": "Караганда"}
                }
              }
            ]
          }
        ]
        </script>
      </body>
    </html>
    """
    scraper = KrishaScraper(city="karaganda", request_delay_sec=0)

    listings = scraper.parse_listing_page(html, category="prodazha")

    assert len(listings) == 1
    assert listings[0].listing_id == "888999"
    assert listings[0].title == "3-комнатная квартира"
    assert listings[0].price == "42000000 KZT"
    assert listings[0].district == "Караганда"


def test_extra_params_from_config_accepts_comma_decimal_values() -> None:
    params = KrishaScraper.extra_params_from_config(
        {
            "area_from": "45,5",
            "kitchen_area_to": "12,3",
        }
    )

    assert params["das[live.square][from]"] == 45.5
    assert params["das[kitchen.square][to]"] == 12.3
