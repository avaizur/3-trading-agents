from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from src.commerce.seasonality import ProductSearchFocus

if TYPE_CHECKING:
    from .adapters.market_research import MarketResearchAdapter


@dataclass(frozen=True)
class MarketListing:
    """Normalized, read-only marketplace search result."""

    title: str
    item_id: str
    price: Decimal
    currency: str
    seller: str | None
    category: str | None
    item_url: str
    condition: str | None
    availability: str | None = None
    end_date: datetime | None = None


class MarketResearchService:
    """Turns Product Scout guidance into deduplicated marketplace candidates."""

    def __init__(self, adapter: "MarketResearchAdapter"):
        self.adapter = adapter

    def find_candidates(
        self,
        focus: ProductSearchFocus,
        *,
        limit_per_search: int = 20,
    ) -> list[MarketListing]:
        searches = [(keyword, None) for keyword in focus.suggested_keywords]
        # Existing profiles use readable category names. Numeric values are treated
        # as eBay taxonomy IDs; names remain useful as ordinary Browse search text.
        searches.extend(
            (None, category) if category.isdigit() else (category, None)
            for category in focus.suggested_categories
        )

        candidates: list[MarketListing] = []
        seen_item_ids: set[str] = set()
        exclusions = tuple(value.casefold() for value in focus.profile.exclusions)
        for keyword, category_id in searches:
            for listing in self.adapter.search(
                keyword=keyword,
                category_id=category_id,
                limit=limit_per_search,
            ):
                if any(value in listing.title.casefold() for value in exclusions):
                    continue
                if listing.item_id not in seen_item_ids:
                    seen_item_ids.add(listing.item_id)
                    candidates.append(listing)
        return candidates
