import importlib
from types import SimpleNamespace


def test_replenishment_refreshes_supplier_cost_and_stock(monkeypatch):
    monkeypatch.setenv("COMMERCE_TABLE_NAME", "test-commerce")
    monkeypatch.setenv("AWS_REGION", "eu-west-2")
    monkeypatch.setenv(
        "EBAY_SECRET_ID",
        "3-trading-agents/ebay-production",
    )

    handler = importlib.import_module(
        "src.lambda.commerce_replenishment.handler"
    )

    product = SimpleNamespace(
        supplier_name="Go Dropship",
        supplier_sku="SKU-1",
        supplier_cost=5.00,
        supplier_stock=1,
        source_url="https://example.com/old",
        market_price_validated=True,
        platform_fees_validated=True,
        return_allowance_validated=True,
        expected_margin=0.25,
    )

    saved_products = []

    class FakeTable:
        def scan(self, **kwargs):
            return {
                "Items": [
                    {
                        "sku": "SKU-1",
                        "offer_id": "OFFER-1",
                        "listing_id": "LISTING-1",
                        "entity_type": "EBAY_LIVE_LISTING",
                    }
                ]
            }

        def update_item(self, **kwargs):
            return {}

    class FakeStore:
        def __init__(self, *args, **kwargs):
            self.table = FakeTable()

        def get_supplier_backed_product(
            self,
            supplier_name,
            sku,
        ):
            return product

        def save_supplier_backed_product(self, item):
            saved_products.append(item)

    class FakeSupplierAdapter:
        def refresh_product(self, sku):
            return SimpleNamespace(
                cost=6.50,
                inventory_count=8,
                supplier_url="https://example.com/fresh",
            )

    monkeypatch.setattr(
        handler,
        "DynamoCommerceStore",
        FakeStore,
    )
    monkeypatch.setattr(
        handler,
        "get_supplier_adapter",
        lambda name, store=None: FakeSupplierAdapter(),
    )
    monkeypatch.setattr(
        handler,
        "load_access_token",
        lambda **kwargs: "TOKEN",
    )
    monkeypatch.setattr(
        handler,
        "get_inventory_quantity",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        handler,
        "load_ebay_adapter",
        lambda secret_id: object(),
    )

    def fake_refresh_product_market(*, product, adapter):
        product.expected_margin = 0.25
        return product, {"refreshed": True}

    monkeypatch.setattr(
        handler,
        "refresh_product_market",
        fake_refresh_product_market,
    )
    monkeypatch.setattr(
        handler,
        "update_live_quantity",
        lambda **kwargs: {"updated": True},
    )

    result = handler.lambda_handler({}, None)

    assert result["ok"] is True
    assert result["results"][0]["replenished"] is True

    assert product.supplier_cost == 6.50
    assert product.supplier_stock == 8
    assert product.source_url == "https://example.com/fresh"

    assert saved_products
    assert saved_products[0].supplier_cost == 6.50
    assert saved_products[0].supplier_stock == 8
