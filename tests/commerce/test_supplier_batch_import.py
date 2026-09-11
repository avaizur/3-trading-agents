import sqlite3

import pytest
from pydantic import ValidationError

from src.commerce.database import CommerceDatabase
from src.commerce.schemas import ProductLane, SupplierBackedProduct
from src.commerce.supplier_batch_import import import_locked_products, main


def test_locked_batch_imports_exact_supplier_facts_and_lanes(tmp_path):
    db_path = tmp_path / "commerce.db"
    imported = import_locked_products(str(db_path))

    assert [(p.supplier_sku, p.product_name, p.supplier_cost, p.lane) for p in imported] == [
        ("PET-73110", "2-in-1 pet feeder", 8.64, ProductLane.EVERGREEN),
        ("PET-73135", "anti-splash cat litter box", 12.68, ProductLane.EVERGREEN),
        ("PET-73719", "large soft pet carrier", 9.65, ProductLane.EVERGREEN),
        ("HOM-55216", "6pc Christmas feather ornaments", 3.94, ProductLane.SEASONAL),
    ]
    assert all(p.supplier_name == "Go Dropship" for p in imported)


def test_import_stays_unvalidated_unprofitable_and_unpublished(tmp_path):
    products = import_locked_products(str(tmp_path / "commerce.db"))

    assert all(p.market_price is None and p.platform_fees is None for p in products)
    assert all(p.return_allowance is None for p in products)
    assert all(not p.market_price_validated for p in products)
    assert all(not p.platform_fees_validated for p in products)
    assert all(not p.return_allowance_validated for p in products)
    assert all(not p.profitable and not p.auto_approved and not p.published for p in products)


def test_batch_import_is_idempotent_and_preserves_validation_state(tmp_path):
    db_path = tmp_path / "commerce.db"
    import_locked_products(str(db_path))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE supplier_backed_products SET market_price = 20, "
            "market_price_validated = 1 WHERE supplier_sku = 'PET-73110'"
        )

    import_locked_products(str(db_path))
    products = CommerceDatabase(str(db_path)).list_supplier_backed_products()
    assert len(products) == 4
    assert products[0].market_price == 20
    assert products[0].market_price_validated is True
    assert products[0].profitable is False


def test_guardrails_reject_premature_profit_or_automation():
    base = dict(
        supplier_name="Go Dropship", supplier_sku="SKU", product_name="Product",
        supplier_cost=1, lane=ProductLane.EVERGREEN,
    )
    with pytest.raises(ValidationError, match="profitability requires validated"):
        SupplierBackedProduct(**base, profitable=True)
    with pytest.raises(ValidationError, match="cannot be auto-approved"):
        SupplierBackedProduct(**base, auto_approved=True)
    with pytest.raises(ValidationError, match="cannot be published"):
        SupplierBackedProduct(**base, published=True)


def test_cli_reports_safe_import(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "commerce.db")]) == 0
    output = capsys.readouterr().out
    assert "Imported 4" in output
    assert "pending validated market price, fees, and return allowance" in output
    assert "No products were approved or published" in output
