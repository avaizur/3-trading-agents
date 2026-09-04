from datetime import datetime, timezone
import pytest

from src.commerce.database import CommerceDatabase
from src.commerce.queue import (
    CandidateQueue,
    InvalidStatusTransitionError,
)
from src.commerce.schemas import (
    CandidateStatus,
    Platform,
    ProductCandidate,
    ProductScoutOpportunity,
    SupplierProduct,
    SupplierType,
)


@pytest.fixture
def queue(tmp_path):
    db_path = tmp_path / "test_queue.db"
    return CandidateQueue(db_path=str(db_path))


def test_enqueue_defaults_to_new(queue):
    candidate = ProductCandidate(
        candidate_id="CAND-001",
        sku="SKU-001",
        title="Test Widget",
        supplier_id="SUP-01",
        supplier_cost=10.0,
        target_price=25.0,
        status=CandidateStatus.VERIFIED,  # Even if passed as VERIFIED, enqueue forces NEW
    )
    enqueued = queue.enqueue(candidate)
    assert enqueued.status == CandidateStatus.NEW
    assert enqueued.candidate_id == "CAND-001"

    loaded = queue.get_candidate("CAND-001")
    assert loaded is not None
    assert loaded.status == CandidateStatus.NEW


def test_enqueue_from_opportunity(queue):
    opp = ProductScoutOpportunity(
        opportunity_id="OPP-101",
        supplier_id="SUP-WHOLESALE-1",
        supplier_sku="SKU-BOTTLE-1",
        title="Insulated Water Bottle",
        category="Kitchen",
        target_platform=Platform.EBAY,
        supplier_cost=8.0,
        estimated_shipping=2.0,
        estimated_platform_fee=3.0,
        estimated_return_buffer=1.0,
        suggested_sale_price=20.0,
        estimated_net_profit=6.0,
        estimated_margin_pct=0.30,
        scouted_at=datetime.now(timezone.utc),
        confidence=0.85,
    )

    candidate = queue.enqueue_from_opportunity(opp)
    assert candidate.candidate_id == "CAND-OPP-101"
    assert candidate.sku == "SKU-BOTTLE-1"
    assert candidate.supplier_cost == 8.0
    assert candidate.target_price == 20.0
    assert candidate.status == CandidateStatus.NEW


def test_happy_path_lifecycle(queue):
    # 1. Enqueue (NEW)
    queue.enqueue(
        ProductCandidate(
            candidate_id="CAND-FLOW",
            sku="SKU-FLOW",
            title="Flow Test Item",
            supplier_id="SUP-1",
            supplier_cost=12.0,
            target_price=28.0,
        )
    )
    assert queue.get_candidate("CAND-FLOW").status == CandidateStatus.NEW

    # 2. Supplier verification (NEW -> VERIFIED)
    supplier_prod = SupplierProduct(
        supplier_id="SUP-1",
        sku="SKU-FLOW",
        title="Flow Test Item",
        supplier_type=SupplierType.WHOLESALE,
        cost=12.0,
        shipping_cost=2.0,
        inventory_count=200,
        lead_time_days=3,
        allows_reselling=True,
    )
    updated, check = queue.verify_supplier("CAND-FLOW", supplier_prod)
    assert updated.status == CandidateStatus.VERIFIED
    assert check.is_valid is True

    # 3. Submit for review (VERIFIED -> REVIEW)
    updated = queue.submit_for_review("CAND-FLOW", notes="Profit margin 35%, ready for review")
    assert updated.status == CandidateStatus.REVIEW
    assert "ready for review" in updated.notes

    # 4. Human approval (REVIEW -> APPROVED_FOR_LISTING)
    updated = queue.approve_for_listing("CAND-FLOW", reviewer="operator_john")
    assert updated.status == CandidateStatus.APPROVED_FOR_LISTING
    assert "operator_john" in updated.notes


def test_reject_from_new_stage(queue):
    queue.enqueue(
        ProductCandidate(
            candidate_id="CAND-REJ-1",
            sku="SKU-REJ-1",
            title="Reject from NEW",
            supplier_id="SUP-1",
            supplier_cost=10.0,
            target_price=20.0,
        )
    )
    rejected = queue.reject("CAND-REJ-1", reason="Unfavorable market saturation")
    assert rejected.status == CandidateStatus.REJECTED
    assert rejected.rejection_reason == "Unfavorable market saturation"


def test_reject_from_verified_stage(queue):
    queue.enqueue(
        ProductCandidate(
            candidate_id="CAND-REJ-2",
            sku="SKU-REJ-2",
            title="Reject from VERIFIED",
            supplier_id="SUP-1",
            supplier_cost=10.0,
            target_price=20.0,
        )
    )
    queue.transition("CAND-REJ-2", CandidateStatus.VERIFIED)
    rejected = queue.reject("CAND-REJ-2", reason="Disqualified after detailed competitor audit")
    assert rejected.status == CandidateStatus.REJECTED
    assert rejected.rejection_reason == "Disqualified after detailed competitor audit"


def test_reject_from_review_stage(queue):
    queue.enqueue(
        ProductCandidate(
            candidate_id="CAND-REJ-3",
            sku="SKU-REJ-3",
            title="Reject from REVIEW",
            supplier_id="SUP-1",
            supplier_cost=10.0,
            target_price=20.0,
        )
    )
    queue.transition("CAND-REJ-3", CandidateStatus.VERIFIED)
    queue.transition("CAND-REJ-3", CandidateStatus.REVIEW)
    rejected = queue.reject("CAND-REJ-3", reason="Human merchant rejected listing")
    assert rejected.status == CandidateStatus.REJECTED
    assert rejected.rejection_reason == "Human merchant rejected listing"


def test_invalid_status_transitions_raise_error(queue):
    queue.enqueue(
        ProductCandidate(
            candidate_id="CAND-INVALID",
            sku="SKU-INV",
            title="Invalid Transition Test",
            supplier_id="SUP-1",
            supplier_cost=10.0,
            target_price=20.0,
        )
    )

    # NEW cannot jump directly to REVIEW without verification
    with pytest.raises(InvalidStatusTransitionError):
        queue.transition("CAND-INVALID", CandidateStatus.REVIEW)

    # NEW cannot jump directly to APPROVED_FOR_LISTING
    with pytest.raises(InvalidStatusTransitionError):
        queue.transition("CAND-INVALID", CandidateStatus.APPROVED_FOR_LISTING)

    # Transition to VERIFIED
    queue.transition("CAND-INVALID", CandidateStatus.VERIFIED)

    # VERIFIED cannot jump directly to APPROVED_FOR_LISTING (must go to REVIEW for human approval)
    with pytest.raises(InvalidStatusTransitionError):
        queue.transition("CAND-INVALID", CandidateStatus.APPROVED_FOR_LISTING)

    # Move to REVIEW then APPROVED_FOR_LISTING
    queue.transition("CAND-INVALID", CandidateStatus.REVIEW)
    queue.transition("CAND-INVALID", CandidateStatus.APPROVED_FOR_LISTING)

    # APPROVED_FOR_LISTING cannot go back to NEW
    with pytest.raises(InvalidStatusTransitionError):
        queue.transition("CAND-INVALID", CandidateStatus.NEW)


def test_verify_supplier_blocks_retail_dropshipping(queue):
    queue.enqueue(
        ProductCandidate(
            candidate_id="CAND-RETAIL-TEST",
            sku="SKU-AMZ-DROP",
            title="Amazon Item For Arbitrage",
            supplier_id="AMAZON-PRIME",
            supplier_cost=15.0,
            target_price=25.0,
        )
    )

    retail_product = SupplierProduct(
        supplier_id="AMAZON-PRIME",
        sku="SKU-AMZ-DROP",
        title="Amazon Item For Arbitrage",
        supplier_type=SupplierType.RETAIL,  # Prohibited retail dropshipping
        cost=15.0,
        shipping_cost=0.0,
        inventory_count=50,
        allows_reselling=True,
    )

    candidate, check = queue.verify_supplier("CAND-RETAIL-TEST", retail_product)

    # Candidate should be automatically REJECTED
    assert candidate.status == CandidateStatus.REJECTED
    assert "Retail-to-retail dropshipping is strictly prohibited" in candidate.rejection_reason

    # Check should be recorded
    assert check.is_valid is False
    assert check.retail_dropshipping_blocked is True
    assert check.candidate_id == "CAND-RETAIL-TEST"

    # Persisted checks in DB
    checks = queue.get_supplier_checks(candidate_id="CAND-RETAIL-TEST")
    assert len(checks) == 1
    assert checks[0].retail_dropshipping_blocked is True


def test_reopen_rejected_candidate(queue):
    queue.enqueue(
        ProductCandidate(
            candidate_id="CAND-REOPEN",
            sku="SKU-REOPEN",
            title="Reopen Test Item",
            supplier_id="SUP-1",
            supplier_cost=10.0,
            target_price=20.0,
        )
    )
    queue.reject("CAND-REOPEN", reason="Initial reject")
    assert queue.get_candidate("CAND-REOPEN").status == CandidateStatus.REJECTED

    reopened = queue.reopen("CAND-REOPEN", notes="New wholesale supplier agreement secured")
    assert reopened.status == CandidateStatus.NEW
    assert "Reopened" in reopened.notes

    # Attempting to reopen a candidate that is already NEW raises InvalidStatusTransitionError
    with pytest.raises(InvalidStatusTransitionError):
        queue.reopen("CAND-REOPEN")


def test_queue_views_and_counts(queue):
    for i in range(10):
        queue.enqueue(
            ProductCandidate(
                candidate_id=f"CAND-BATCH-{i}",
                sku=f"SKU-BATCH-{i}",
                title=f"Item {i}",
                supplier_id="SUP-BATCH",
                supplier_cost=10.0,
                target_price=25.0,
            )
        )

    # Initially 10 NEW
    assert len(queue.get_new()) == 10
    assert len(queue.get_verified()) == 0
    assert len(queue.get_review()) == 0
    assert len(queue.get_approved()) == 0
    assert len(queue.get_rejected()) == 0

    # Advance candidates
    queue.transition("CAND-BATCH-0", CandidateStatus.VERIFIED)
    queue.transition("CAND-BATCH-1", CandidateStatus.VERIFIED)
    queue.transition("CAND-BATCH-1", CandidateStatus.REVIEW)
    queue.transition("CAND-BATCH-2", CandidateStatus.VERIFIED)
    queue.transition("CAND-BATCH-2", CandidateStatus.REVIEW)
    queue.transition("CAND-BATCH-2", CandidateStatus.APPROVED_FOR_LISTING)
    queue.reject("CAND-BATCH-3", reason="Low margin")

    assert len(queue.get_new()) == 6
    assert len(queue.get_verified()) == 1
    assert len(queue.get_review()) == 1
    assert len(queue.get_approved()) == 1
    assert len(queue.get_rejected()) == 1

    counts = queue.count_by_status()
    assert counts["NEW"] == 6
    assert counts["VERIFIED"] == 1
    assert counts["REVIEW"] == 1
    assert counts["APPROVED_FOR_LISTING"] == 1
    assert counts["REJECTED"] == 1


def test_nonexistent_candidate_raises_key_error(queue):
    with pytest.raises(KeyError):
        queue.transition("NONEXISTENT", CandidateStatus.VERIFIED)

    with pytest.raises(KeyError):
        queue.verify_supplier(
            "NONEXISTENT",
            SupplierProduct(
                supplier_id="SUP-1",
                sku="SKU-X",
                title="Widget",
                supplier_type=SupplierType.WHOLESALE,
                cost=10.0,
            ),
        )
