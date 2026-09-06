import json

import pytest

from src.commerce.database import CommerceDatabase
from src.commerce.ebay_listing_draft_cli import create_listing_draft, main
from src.commerce.schemas import (
    CandidateStatus,
    Platform,
    ProductCandidate,
    SupplierProfitStatus,
)


def _candidate(candidate_id="CAND-EBAY-123456"):
    return ProductCandidate(
        candidate_id=candidate_id,
        sku="SUP-SKU-9",
        title="Verified profitable widget",
        supplier_id="Acme Wholesale",
        supplier_cost=10.0,
        target_price=25.0,
        shipping_cost=2.0,
        estimated_fee=3.0,
        estimated_profit=10.0,
        estimated_margin_pct=0.4,
        supplier_profit_status=SupplierProfitStatus.VERIFIED_PROFITABLE,
        status=CandidateStatus.APPROVED_FOR_LISTING,
    )


def test_command_prints_ebay_ready_draft_and_persists_it(tmp_path, capsys):
    db_path = tmp_path / "commerce.db"
    db = CommerceDatabase(str(db_path))
    candidate = _candidate()
    db.save_candidate(candidate)

    assert main(["--db", str(db_path), "--quantity", "3"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "ebay_item_or_candidate_id": "123456",
        "title": "Verified profitable widget",
        "supplier_name": "Acme Wholesale",
        "supplier_sku": "SUP-SKU-9",
        "sale_price": 25.0,
        "quantity": 3,
        "description": "Product: Verified profitable widget\nSupplier: Acme Wholesale\nSupplier SKU: SUP-SKU-9",
        "category_placeholder": "General Merchandise > Default Category",
        "shipping_placeholder": "Standard Shipping (Placeholder)",
        "expected_profit": 10.0,
        "expected_margin": "40.00%",
    }
    saved = CommerceDatabase(str(db_path)).get_draft_by_candidate_id(
        candidate.candidate_id
    )
    assert saved is not None
    assert saved.quantity == 3


def test_selects_only_verified_profitable_approved_candidate(tmp_path):
    db = CommerceDatabase(str(tmp_path / "commerce.db"))
    db.save_candidate(
        _candidate("CAND-EBAY-NOT-PROFITABLE").model_copy(
            update={"supplier_profit_status": SupplierProfitStatus.VERIFIED_LOW_MARGIN}
        )
    )
    db.save_candidate(
        _candidate("CAND-AMAZON-PROFITABLE").model_copy(
            update={"target_platform": Platform.AMAZON}
        )
    )
    expected = db.save_candidate(_candidate("CAND-EBAY-ELIGIBLE"))

    output = create_listing_draft(str(tmp_path / "commerce.db"))

    assert output["ebay_item_or_candidate_id"] == "ELIGIBLE"
    assert db.get_draft_by_candidate_id(expected.candidate_id) is not None


def test_does_not_bypass_existing_listing_approval_rule(tmp_path):
    db_path = tmp_path / "commerce.db"
    db = CommerceDatabase(str(db_path))
    db.save_candidate(
        _candidate().model_copy(update={"status": CandidateStatus.VERIFIED})
    )

    with pytest.raises(ValueError, match="APPROVED_FOR_LISTING"):
        create_listing_draft(str(db_path))

    assert db.list_drafts() == []


def test_uses_only_available_persisted_product_and_supplier_facts(tmp_path):
    db_path = tmp_path / "commerce.db"
    db = CommerceDatabase(str(db_path))
    candidate = _candidate().model_copy(update={
        "title": "  Pumpkin   Lights |  Indoor / Outdoor  ",
        "category": "Home & Garden > Holiday Decorations",
    })
    db.save_candidate(candidate)
    db.record_manual_supplier_match({
        "ebay_item_id": "123456",
        "supplier_name": "Acme Wholesale",
        "sku": "SUP-SKU-9",
        "cost": 10.0,
        "shipping": 2.0,
        "stock": 7,
        "direct_ship": True,
        "verification_status": "VERIFIED",
        "supplier_status": "VERIFIED_PROFITABLE",
        "expected_profit": 10.0,
        "expected_margin": 0.4,
        "final_outcome": "verified",
    })

    output = create_listing_draft(str(db_path))

    assert output["title"] == "Pumpkin Lights | Indoor / Outdoor"
    assert output["category_placeholder"] == "Home & Garden > Holiday Decorations"
    assert output["shipping_placeholder"] == "Supplier shipping cost: 2.00"
    assert output["description"] == (
        "Product: Pumpkin Lights | Indoor / Outdoor\n"
        "Supplier: Acme Wholesale\nSupplier SKU: SUP-SKU-9\n"
        "Supplier stock confirmed: 7"
    )
    assert "brand new" not in output["description"].casefold()
    assert "guarante" not in output["description"].casefold()


def test_keeps_placeholders_when_category_and_shipping_facts_are_unavailable(tmp_path):
    db = CommerceDatabase(str(tmp_path / "commerce.db"))
    db.save_candidate(_candidate())

    output = create_listing_draft(str(tmp_path / "commerce.db"))

    assert output["category_placeholder"] == "General Merchandise > Default Category"
    assert output["shipping_placeholder"] == "Standard Shipping (Placeholder)"
