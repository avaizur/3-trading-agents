import csv

from src.commerce.schemas import MarketValidationStatus, ProductLane
from scripts.import_supplier_catalog_csv import import_catalog


class FakeStore:
    def __init__(self):
        self.products = {}

    def get_supplier_backed_product(self, supplier_name, supplier_sku):
        return self.products.get((supplier_name, supplier_sku))

    def save_supplier_backed_product(self, product):
        self.products[(product.supplier_name, product.supplier_sku)] = product
        return product


def test_imported_product_starts_pending(tmp_path, monkeypatch):
    path = tmp_path / "catalogue.csv"

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sku", "title", "cost"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "sku": "TEST-001",
                "title": "Test Supplier Product",
                "cost": "5.50",
            }
        )

    fake = FakeStore()

    monkeypatch.setattr(
        "scripts.import_supplier_catalog_csv.DynamoCommerceStore",
        lambda table_name: fake,
    )

    imported, skipped = import_catalog(
        str(path),
        table_name="test-table",
        supplier_name="Test Supplier",
        lane=ProductLane.EVERGREEN,
        sku_column="sku",
        title_column="title",
        cost_column="cost",
    )

    assert imported == 1
    assert skipped == 0

    product = fake.products[("Test Supplier", "TEST-001")]

    assert product.market_validation_status is MarketValidationStatus.PENDING
    assert product.profitable is False
    assert product.auto_approved is False
    assert product.published is False


def test_existing_product_is_skipped(tmp_path, monkeypatch):
    path = tmp_path / "catalogue.csv"

    path.write_text(
        "sku,title,cost\nTEST-001,Test Product,5.50\n",
        encoding="utf-8",
    )

    fake = FakeStore()

    class Existing:
        pass

    fake.products[("Test Supplier", "TEST-001")] = Existing()

    monkeypatch.setattr(
        "scripts.import_supplier_catalog_csv.DynamoCommerceStore",
        lambda table_name: fake,
    )

    imported, skipped = import_catalog(
        str(path),
        table_name="test-table",
        supplier_name="Test Supplier",
        lane=ProductLane.EVERGREEN,
        sku_column="sku",
        title_column="title",
        cost_column="cost",
    )

    assert imported == 0
    assert skipped == 1
