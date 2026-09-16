from datetime import date
from decimal import Decimal

from src.commerce.adapters.market_research import MarketResearchAdapter
from src.commerce.agents.product_scout import ProductScoutAgent
from src.commerce.market_research import MarketListing


class FakeMarketAdapter(MarketResearchAdapter):
    def search(self, *, keyword=None, category_id=None, limit=20):
        identity = keyword or category_id or "market"

        return [
            MarketListing(
                title=f"{identity} decoration",
                item_id=f"{identity}-1",
                price=Decimal("9.99"),
                currency="GBP",
                seller="seller_one",
                category="Decorations",
                item_url="https://example.test/1",
                condition="New",
                availability="IN_STOCK",
            ),
            MarketListing(
                title=f"{identity} premium decoration",
                item_id=f"{identity}-2",
                price=Decimal("14.99"),
                currency="GBP",
                seller="seller_two",
                category="Decorations",
                item_url="https://example.test/2",
                condition="New",
                availability="IN_STOCK",
            ),
        ]


def test_product_scout_researches_and_scores_market():
    results = ProductScoutAgent().research_market(
        FakeMarketAdapter(),
        as_of=date(2026, 9, 5),
        limit_per_search=5,
        top_n=5,
    )

    assert results
    assert len(results) <= 5

    assert results == sorted(
        results,
        key=lambda item: (-item.overall_score, item.listing.item_id),
    )

    for result in results:
        assert 0 <= result.overall_score <= 100
        assert result.listing.currency == "GBP"


def test_product_scout_research_respects_top_n():
    results = ProductScoutAgent().research_market(
        FakeMarketAdapter(),
        as_of=date(2026, 9, 5),
        top_n=2,
    )

    assert len(results) == 2
