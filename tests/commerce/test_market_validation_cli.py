import json

import pytest

from src.commerce.database import CommerceDatabase
from src.commerce.market_validation_cli import (
    load_validation_inputs,
    main,
    validate_market_batch,
)
from src.commerce.schemas import MarketValidationStatus, SupplierMarketValidationInput
from src.commerce.supplier_batch_import import import_locked_products


def validation(sku, price, fee, returns):
    return SupplierMarketValidationInput(
        supplier_name="Go Dropship", supplier_sku=sku,
        marketplace_sale_price=price, platform_fee_estimate=fee,
        return_allowance=returns,
    )


def test_batch_uses_existing_profit_rules_and_persists_pass_and_reject(tmp_path):
    db_path = str(tmp_path / "commerce.db")
    import_locked_products(db_path)

    results = validate_market_batch(db_path, [
        validation("PET-73110", 20, 2, 1),
        validation("PET-73135", 15, 1, 1),
    ])

    assert [(r.status, r.expected_profit, r.expected_margin) for r in results] == [
        (MarketValidationStatus.PASS, 8.36, 0.418),
        (MarketValidationStatus.REJECT, 0.32, 0.0213),
    ]
    db = CommerceDatabase(db_path)
    passed = db.get_supplier_backed_product("Go Dropship", "PET-73110")
    rejected = db.get_supplier_backed_product("Go Dropship", "PET-73135")
    assert passed.market_validation_status is MarketValidationStatus.PASS
    assert passed.profitable is True
    assert rejected.market_validation_status is MarketValidationStatus.REJECT
    assert rejected.profitable is False
    assert len(db.get_supplier_market_validations("Go Dropship", "PET-73110")) == 1


def test_validation_preserves_locked_facts_lane_and_safety_flags(tmp_path):
    db_path = str(tmp_path / "commerce.db")
    original = import_locked_products(db_path)[3]

    validate_market_batch(db_path, [validation("HOM-55216", 10, 1, 0.5)])
    updated = CommerceDatabase(db_path).get_supplier_backed_product(
        "Go Dropship", "HOM-55216"
    )

    assert (updated.supplier_name, updated.supplier_sku, updated.product_name) == (
        original.supplier_name, original.supplier_sku, original.product_name,
    )
    assert updated.supplier_cost == original.supplier_cost
    assert updated.lane == original.lane
    assert updated.auto_approved is False
    assert updated.published is False
    assert updated.market_price_validated is True
    assert updated.platform_fees_validated is True
    assert updated.return_allowance_validated is True


def test_invalid_or_unknown_input_does_not_persist_partial_batch(tmp_path):
    db_path = str(tmp_path / "commerce.db")
    import_locked_products(db_path)
    with pytest.raises(KeyError, match="not found"):
        validate_market_batch(db_path, [
            validation("PET-73110", 20, 2, 1),
            validation("MISSING", 20, 2, 1),
        ])

    product = CommerceDatabase(db_path).get_supplier_backed_product(
        "Go Dropship", "PET-73110"
    )
    assert product.market_validation_status is MarketValidationStatus.PENDING
    assert product.expected_profit is None


@pytest.mark.parametrize("field,value", [
    ("marketplace_sale_price", 0),
    ("platform_fee_estimate", -1),
    ("return_allowance", -1),
])
def test_loader_rejects_non_real_economic_values(tmp_path, field, value):
    row = {
        "supplier_name": "Go Dropship", "supplier_sku": "PET-73110",
        "marketplace_sale_price": 20, "platform_fee_estimate": 2,
        "return_allowance": 1,
    }
    row[field] = value
    path = tmp_path / "validation.json"
    path.write_text(json.dumps([row]), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid market validation input"):
        load_validation_inputs(str(path))


def test_cli_loads_batch_and_reports_no_approval_or_publish(tmp_path, capsys):
    db_path = str(tmp_path / "commerce.db")
    import_locked_products(db_path)
    path = tmp_path / "validation.json"
    path.write_text(json.dumps({"validations": [{
        "supplier_name": "Go Dropship", "supplier_sku": "PET-73719",
        "marketplace_sale_price": 20, "platform_fee_estimate": 2,
        "return_allowance": 1,
    }]}), encoding="utf-8")

    assert main([str(path), "--db", db_path]) == 0
    output = capsys.readouterr().out
    assert "PET-73719: PASS" in output
    assert "No products were approved or published" in output
