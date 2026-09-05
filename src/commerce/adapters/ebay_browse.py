import json
import os
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.commerce.market_research import MarketListing

from .market_research import MarketResearchAdapter


JsonTransport = Callable[[str, dict[str, str], float], dict[str, Any]]


def _get_json(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed API base
        return json.loads(response.read().decode("utf-8"))


class EBayBrowseResearchAdapter(MarketResearchAdapter):
    """Read-only client for eBay Browse API item-summary search."""

    API_BASE_URL = "https://api.ebay.com/buy/browse/v1"

    def __init__(
        self,
        *,
        transport: JsonTransport | None = None,
        timeout: float = 10.0,
    ):
        access_token = os.environ.get("EBAY_ACCESS_TOKEN")
        if not access_token:
            raise RuntimeError("EBAY_ACCESS_TOKEN environment variable is required")
        self._access_token = access_token
        self.marketplace_id = os.environ.get("EBAY_MARKETPLACE_ID", "EBAY_GB")
        self._transport = transport or _get_json
        self.timeout = timeout

    def search(
        self,
        *,
        keyword: str | None = None,
        category_id: str | None = None,
        limit: int = 20,
    ) -> list[MarketListing]:
        if not keyword and not category_id:
            raise ValueError("keyword or category_id is required")
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

        params = {"limit": str(limit)}
        if keyword:
            params["q"] = keyword
        if category_id:
            params["category_ids"] = category_id
        url = f"{self.API_BASE_URL}/item_summary/search?{urlencode(params)}"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
        }
        payload = self._transport(url, headers, self.timeout)
        return [self._normalize(item) for item in payload.get("itemSummaries", [])]

    @staticmethod
    def _normalize(item: dict[str, Any]) -> MarketListing:
        price = item.get("price") or {}
        try:
            amount = Decimal(str(price["value"]))
        except (KeyError, InvalidOperation) as exc:
            raise ValueError("eBay result is missing a valid price") from exc

        categories = item.get("categories") or []
        category = categories[0].get("categoryName") if categories else None
        seller = item.get("seller") or {}
        availability = item.get("estimatedAvailabilities") or []
        availability_status = (
            availability[0].get("estimatedAvailabilityStatus") if availability else None
        )
        return MarketListing(
            title=item["title"],
            item_id=item["itemId"],
            price=amount,
            currency=price["currency"],
            seller=seller.get("username"),
            category=category,
            item_url=item["itemWebUrl"],
            condition=item.get("condition"),
            availability=availability_status,
            end_date=_parse_datetime(item.get("itemEndDate")),
        )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
