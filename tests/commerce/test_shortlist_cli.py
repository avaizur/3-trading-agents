import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.commerce.adapters.market_research import MarketResearchAdapter
from src.commerce.manual_supplier_cli import load_shortlist
from src.commerce.market_research import MarketListing
from src.commerce.shortlist_cli import export_shortlist


class FakeResearchAdapter(MarketResearchAdapter):
    def __init__(self, listings):
        self.listings = listings
        self.searches = []

    def search(self, *, keyword=None, category_id=None, limit=20):
        self.searches.append((keyword, category_id, limit))
        return self.listings[:limit] if len(self.searches) == 1 else []


def _listing(index):
    return MarketListing(
        title=f"Halloween pumpkin decor lights {index}",
        item_id=str(index),
        price=Decimal(str(10 + index)),
        currency="GBP",
        seller=f"seller-{index}",
        category=f"Halloween Decorations {index}",
        item_url=f"https://www.ebay.co.uk/itm/{index}",
        condition="New",
        availability="IN_STOCK",
        end_date=datetime(2026, 10, 20, tzinfo=timezone.utc),
    )


def test_export_shortlist_writes_ranked_manual_verification_records(tmp_path):
    adapter = FakeResearchAdapter([_listing(index) for index in range(12)])
    output = tmp_path / "shortlist.json"

    count = export_shortlist(
        adapter, output, top_n=5, limit_per_search=12, as_of=date(2026, 9, 5)
    )

    raw = json.loads(output.read_text(encoding="utf-8"))
    loaded = load_shortlist(str(output))
    assert count == len(raw) == len(loaded) == 5
    assert [row["overall_score"] for row in raw] == sorted(
        (row["overall_score"] for row in raw), reverse=True
    )
    assert set(raw[0]) == {
        "listing", "seasonal_relevance", "price_attractiveness",
        "competition_density", "signal_quality", "data_completeness",
        "overall_score", "decision", "reasons",
    }
    assert set(raw[0]["listing"]) == {
        "title", "item_id", "price", "currency", "seller", "category",
        "item_url", "condition", "availability", "end_date",
    }
    assert all(row["decision"] == "SHORTLIST" for row in raw)
    assert adapter.searches[0][2] == 12


def test_export_shortlist_excludes_non_shortlist_scores(tmp_path):
    output = tmp_path / "shortlist.json"
    incomplete = MarketListing(
        title="Unrelated item", item_id="low", price=Decimal("10"),
        currency="GBP", seller=None, category=None, item_url="not-https",
        condition=None,
    )

    count = export_shortlist(
        FakeResearchAdapter([incomplete]), output, top_n=5,
        as_of=date(2026, 9, 5),
    )

    assert count == 0
    assert json.loads(output.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("top_n", [4, 11])
def test_export_shortlist_requires_five_to_ten_candidates(tmp_path, top_n):
    with pytest.raises(ValueError, match="between 5 and 10"):
        export_shortlist(FakeResearchAdapter([]), tmp_path / "out.json", top_n=top_n)
