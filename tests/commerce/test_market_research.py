from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from src.commerce.adapters.ebay_browse import EBayBrowseResearchAdapter
from src.commerce.adapters.market_research import MarketResearchAdapter
from src.commerce.market_research import MarketListing, MarketResearchService
from src.commerce.product_scout import get_current_search_focus
from src.commerce.seasonality import ProductSearchFocus, ProductSearchProfile


def test_ebay_browse_search_is_get_shaped_and_normalizes_results(monkeypatch):
    monkeypatch.setenv("EBAY_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("EBAY_MARKETPLACE_ID", "EBAY_GB")
    captured = {}

    def mock_transport(url, headers, timeout):
        captured.update(url=url, headers=headers, timeout=timeout)
        return {
            "itemSummaries": [
                {
                    "itemId": "v1|123|0",
                    "title": "LED Pumpkin Lights",
                    "price": {"value": "12.99", "currency": "GBP"},
                    "seller": {"username": "seasonal_shop"},
                    "categories": [
                        {"categoryId": "166725", "categoryName": "Decorations"}
                    ],
                    "itemWebUrl": "https://www.ebay.co.uk/itm/123",
                    "condition": "New",
                    "estimatedAvailabilities": [
                        {"estimatedAvailabilityStatus": "IN_STOCK"}
                    ],
                    "itemEndDate": "2026-10-20T18:30:00.000Z",
                }
            ]
        }

    adapter = EBayBrowseResearchAdapter(transport=mock_transport)
    results = adapter.search(keyword="pumpkin lights", category_id="166725", limit=10)

    query = parse_qs(urlparse(captured["url"]).query)
    assert urlparse(captured["url"]).path.endswith("/item_summary/search")
    assert query == {
        "q": ["pumpkin lights"],
        "category_ids": ["166725"],
        "limit": ["10"],
    }
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["headers"]["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB"
    assert results == [
        MarketListing(
            title="LED Pumpkin Lights",
            item_id="v1|123|0",
            price=Decimal("12.99"),
            currency="GBP",
            seller="seasonal_shop",
            category="Decorations",
            item_url="https://www.ebay.co.uk/itm/123",
            condition="New",
            availability="IN_STOCK",
            end_date=datetime(2026, 10, 20, 18, 30, tzinfo=timezone.utc),
        )
    ]


def test_ebay_browse_credentials_come_from_environment(monkeypatch):
    monkeypatch.delenv("EBAY_ACCESS_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="EBAY_ACCESS_TOKEN"):
        EBayBrowseResearchAdapter(transport=lambda *_: {})


def test_ebay_browse_search_validates_read_query(monkeypatch):
    monkeypatch.setenv("EBAY_ACCESS_TOKEN", "test-token")
    adapter = EBayBrowseResearchAdapter(transport=lambda *_: {})

    with pytest.raises(ValueError, match="keyword or category_id"):
        adapter.search()
    with pytest.raises(ValueError, match="between 1 and 200"):
        adapter.search(keyword="gift", limit=201)


class FakeResearchAdapter(MarketResearchAdapter):
    def __init__(self):
        self.searches = []

    def search(self, *, keyword=None, category_id=None, limit=20):
        self.searches.append((keyword, category_id, limit))
        identity = keyword or category_id
        return [
            MarketListing(
                title=f"Result for {identity}",
                item_id="duplicate" if len(self.searches) < 3 else str(len(self.searches)),
                price=Decimal("9.99"),
                currency="GBP",
                seller=None,
                category=None,
                item_url=f"https://example.test/{len(self.searches)}",
                condition=None,
            )
        ]


def test_market_research_service_uses_focus_and_deduplicates_candidates():
    focus = get_current_search_focus(date(2026, 9, 5))
    assert focus is not None
    adapter = FakeResearchAdapter()

    results = MarketResearchService(adapter).find_candidates(focus, limit_per_search=5)

    expected_search_count = len(focus.suggested_keywords) + len(focus.suggested_categories)
    assert len(adapter.searches) == expected_search_count
    assert adapter.searches[0] == (focus.suggested_keywords[0], None, 5)
    assert adapter.searches[-1] == (focus.suggested_categories[-1], None, 5)
    assert len(results) == expected_search_count - 1
    assert len({result.item_id for result in results}) == len(results)


def test_market_research_service_filters_profile_exclusions():
    base_focus = get_current_search_focus(date(2026, 9, 5))
    assert base_focus is not None
    focus = ProductSearchFocus(
        opportunity=base_focus.opportunity,
        profile=ProductSearchProfile(
            event_key="halloween",
            categories=("Decor",),
            keywords=("costume",),
            exclusions=("result",),
            priority_score=50,
        ),
    )

    assert MarketResearchService(FakeResearchAdapter()).find_candidates(focus) == []
