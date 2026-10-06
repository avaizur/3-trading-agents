from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any
from urllib.error import HTTPError

BASE_URL = "https://api.ebay.com/sell/fulfillment/v1"


class EBayOrderError(RuntimeError):
    """Raised for safe eBay Fulfillment API failures."""


def _request(
    path: str,
    token: str,
    *,
    opener=urllib.request.urlopen,
) -> dict[str, Any]:
    request = urllib.request.Request(
        BASE_URL + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
        },
        method="GET",
    )

    try:
        with opener(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    except HTTPError as exc:
        raise EBayOrderError(
            f"eBay Fulfillment API returned HTTP {exc.code}"
        ) from None
    except Exception as exc:
        raise EBayOrderError(
            f"Unable to read eBay orders: {type(exc).__name__}"
        ) from None


def get_unfulfilled_orders(
    token: str,
    *,
    limit: int = 50,
    opener=urllib.request.urlopen,
) -> list[dict[str, Any]]:
    if not token:
        raise ValueError("eBay access token is required")

    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")

    filter_value = "orderfulfillmentstatus:{NOT_STARTED|IN_PROGRESS}"

    query = urllib.parse.urlencode(
        {
            "filter": filter_value,
            "limit": str(limit),
            "offset": "0",
        }
    )

    payload = _request(
        f"/order?{query}",
        token,
        opener=opener,
    )

    orders = payload.get("orders", [])

    if not isinstance(orders, list):
        raise EBayOrderError("eBay orders response was invalid")

    return [
        order
        for order in orders
        if isinstance(order, dict)
    ]
