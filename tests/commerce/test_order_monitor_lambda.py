import importlib.util
from pathlib import Path

from botocore.exceptions import ClientError


HANDLER_PATH = (
    Path(__file__).parents[2]
    / "src"
    / "lambda"
    / "commerce_order_monitor"
    / "handler.py"
)

spec = importlib.util.spec_from_file_location(
    "commerce_order_monitor_handler",
    HANDLER_PATH,
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        key = Item["PK"]

        if key in self.items:
            raise ClientError(
                {
                    "Error": {
                        "Code": "ConditionalCheckFailedException",
                        "Message": "Already exists",
                    }
                },
                "PutItem",
            )

        self.items[key] = Item


def test_claim_order_is_duplicate_safe():
    table = FakeTable()

    order = {
        "orderId": "13-15254-19243",
        "creationDate": "2026-10-06T08:15:34.000Z",
        "orderFulfillmentStatus": "NOT_STARTED",
        "lineItems": [
            {
                "sku": "BAG-76380",
                "title": '17" Tool Bag',
                "quantity": 1,
            }
        ],
    }

    assert module._claim_order(table, order) is True
    assert module._claim_order(table, order) is False

    stored = table.items["EBAY_ORDER#13-15254-19243"]

    assert stored["entity_type"] == "EBAY_ORDER"
    assert stored["line_items"][0]["sku"] == "BAG-76380"
    assert stored["supplier_ordering_performed"] is False


def test_alert_contains_order_but_no_buyer_details():
    order = {
        "orderId": "13-15254-19243",
        "creationDate": "2026-10-06T08:15:34.000Z",
        "orderFulfillmentStatus": "NOT_STARTED",
        "lineItems": [
            {
                "sku": "BAG-76380",
                "title": '17" Tool Bag',
                "quantity": 1,
            }
        ],
        "buyer": {
            "username": "must-not-appear",
        },
        "fulfillmentStartInstructions": [
            {
                "shippingStep": {
                    "shipTo": {
                        "fullName": "must-not-appear",
                    }
                }
            }
        ],
    }

    message = module._format_alert([order])

    assert "13-15254-19243" in message
    assert "BAG-76380" in message
    assert '17" Tool Bag' in message
    assert "quantity 1" in message
    assert "must-not-appear" not in message
    assert "No supplier order was placed automatically." in message
