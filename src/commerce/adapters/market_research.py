from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.commerce.market_research import MarketListing


class MarketResearchAdapter(ABC):
    """Read-only marketplace adapter for keyword and category research."""

    @abstractmethod
    def search(
        self,
        *,
        keyword: str | None = None,
        category_id: str | None = None,
        limit: int = 20,
    ) -> list["MarketListing"]:
        raise NotImplementedError
