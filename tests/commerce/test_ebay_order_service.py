import json
from urllib.parse import parse_qs, urlparse

import pytest

from src.commerce.ebay_order_service import get_unfulfilled_orders


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_get_unfulfilled_orders_uses_fulfillment_filter():
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["auth"] = request.headers["Authorization"]
        captured["timeout"] = timeout

        return FakeResponse(
            {
                "orders": [
                    {
                        "orderId": "13-15254-19243",
                        "orderFulfillmentStatus": "NOT_STARTED",
                        "lineItems": [
                            {
                                "sku": "BAG-76380",
                                "quantity": 1,
                            }
                        ],
                    }
                ]
            }
        )

    orders = get_unfulfilled_orders(
        "secret-access-token",
        opener=opener,
    )

    assert len(orders) == 1
    assert orders[0]["orderId"] == "13-15254-19243"
    assert orders[0]["lineItems"][0]["sku"] == "BAG-76380"

    parsed = urlparse(captured["url"])
    query = parse_qs(parsed.query)

    assert query["filter"] == [
        "orderfulfillmentstatus:{NOT_STARTED|IN_PROGRESS}"
    ]
    assert query["limit"] == ["50"]
    assert captured["auth"] == "Bearer secret-access-token"
    assert captured["timeout"] == 30


def test_get_unfulfilled_orders_rejects_bad_limit():
    with pytest.raises(ValueError):
        get_unfulfilled_orders("token", limit=0)
