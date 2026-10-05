import pytest

import src.commerce.ebay_inventory_service as service


def test_update_live_quantity_calls_bulk_endpoint(monkeypatch):
    captured = {}

    def fake_request(method, path, token, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["token"] = token
        captured["payload"] = payload

        return {
            "responses": [
                {
                    "sku": "SKU-1",
                    "statusCode": 200,
                }
            ]
        }

    monkeypatch.setattr(service, "_request", fake_request)

    result = service.update_live_quantity(
        sku="SKU-1",
        offer_id="12345",
        quantity=1,
        token="TEST-TOKEN",
    )

    assert result["updated"] is True
    assert result["quantity"] == 1
    assert captured["method"] == "POST"
    assert captured["path"] == "/bulk_update_price_quantity"
    assert captured["payload"]["requests"][0]["sku"] == "SKU-1"
    assert (
        captured["payload"]["requests"][0]
        ["shipToLocationAvailability"]["quantity"]
        == 1
    )
    assert (
        captured["payload"]["requests"][0]
        ["offers"][0]["availableQuantity"]
        == 1
    )


def test_update_live_quantity_rejects_negative_quantity():
    with pytest.raises(ValueError):
        service.update_live_quantity(
            sku="SKU-1",
            offer_id="12345",
            quantity=-1,
            token="TEST-TOKEN",
        )
