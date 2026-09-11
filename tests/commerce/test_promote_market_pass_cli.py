from src.commerce.approve_candidate_cli import approve_candidate
from src.commerce.database import CommerceDatabase
from src.commerce.ebay_listing_draft_cli import create_listing_draft
from src.commerce.market_validation_cli import validate_market_batch
from src.commerce.promote_market_pass_cli import main, promote_market_pass_products
from src.commerce.schemas import (
    CandidateStatus,
    SupplierMarketValidationInput,
    SupplierProfitStatus,
)
from src.commerce.supplier_batch_import import import_locked_products


def validated(sku, price, fee, returns):
    return SupplierMarketValidationInput(
        supplier_name="Go Dropship", supplier_sku=sku,
        marketplace_sale_price=price, platform_fee_estimate=fee,
        return_allowance=returns,
    )


def setup_validations(db_path):
    import_locked_products(db_path)
    validate_market_batch(db_path, [
        validated("PET-73110", 19.99, 3.66, 1.00),
        validated("PET-73135", 21.99, 3.98, 1.10),
        validated("PET-73719", 19.99, 3.66, 1.60),
        validated("HOM-55216", 12.97, 2.39, 0.65),
    ])


def test_batch_moves_only_pass_products_to_review(tmp_path):
    db_path = str(tmp_path / "commerce.db")
    setup_validations(db_path)

    candidates = promote_market_pass_products(db_path)

    assert [candidate.sku for candidate in candidates] == [
        "PET-73110", "PET-73719", "HOM-55216",
    ]
    assert all(candidate.status is CandidateStatus.REVIEW for candidate in candidates)
    assert all(
        candidate.supplier_profit_status is SupplierProfitStatus.VERIFIED_PROFITABLE
        for candidate in candidates
    )
    db = CommerceDatabase(db_path)
    assert db.get_candidates_by_sku("PET-73135") == []
    assert db.list_drafts() == []


def test_promotion_preserves_supplier_facts_lane_economics_and_is_idempotent(tmp_path):
    db_path = str(tmp_path / "commerce.db")
    setup_validations(db_path)
    first = promote_market_pass_products(db_path)
    second = promote_market_pass_products(db_path)

    assert [c.candidate_id for c in first] == [c.candidate_id for c in second]
    assert len(CommerceDatabase(db_path).list_candidates()) == 3
    feeder = CommerceDatabase(db_path).get_candidates_by_sku("PET-73110")[0]
    assert feeder.supplier_id == "Go Dropship"
    assert feeder.supplier_cost == 8.64
    assert feeder.target_price == 19.99
    assert feeder.estimated_fee == 3.66
    assert feeder.estimated_profit == 6.69
    assert feeder.estimated_margin_pct == 0.3347
    assert "lane EVERGREEN" in feeder.notes


def test_explicit_sku_approval_then_sku_draft_reuses_existing_guards(tmp_path):
    db_path = str(tmp_path / "commerce.db")
    setup_validations(db_path)
    promote_market_pass_products(db_path)

    before, after = approve_candidate(
        db_path=db_path, sku="PET-73110", reviewer="human-alice"
    )
    payload = create_listing_draft(db_path, sku="PET-73110")

    assert before is CandidateStatus.REVIEW
    assert after is CandidateStatus.APPROVED_FOR_LISTING
    assert payload["supplier_sku"] == "PET-73110"
    assert payload["expected_profit"] == 6.69
    assert payload["expected_margin"] == "33.47%"
    candidate = CommerceDatabase(db_path).get_candidates_by_sku("PET-73110")[0]
    assert "Approved by human-alice" in candidate.notes


def test_cli_reports_review_without_approval_or_publish(tmp_path, capsys):
    db_path = str(tmp_path / "commerce.db")
    setup_validations(db_path)

    assert main(["--db", db_path]) == 0
    output = capsys.readouterr().out
    assert "PET-73110: REVIEW" in output
    assert "PET-73135" not in output
    assert "No products were approved or published" in output
