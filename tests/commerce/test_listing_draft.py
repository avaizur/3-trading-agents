from datetime import datetime, timezone
import pytest

from src.commerce.adapters.ebay import EBayAdapter
from src.commerce.database import CommerceDatabase
from src.commerce.queue import (
    CandidateQueue,
    InvalidDraftStatusTransitionError,
)
from src.commerce.schemas import (
    CandidateStatus,
    DraftReviewStatus,
    EBayListingDraft,
    ListingStatus,
    Platform,
    ProductCandidate,
    SupplierProfitStatus,
)
from src.commerce.seller_a import create_ebay_draft


@pytest.fixture
def approved_candidate():
    return ProductCandidate(
        candidate_id="CAND-APP-01",
        sku="SKU-TUMBLER-BLK",
        title="Matte Black 20oz Insulated Tumbler",
        supplier_id="WHOLESALE-DIRECT-01",
        target_platform=Platform.EBAY,
        supplier_cost=10.00,
        target_price=24.99,
        shipping_cost=3.50,
        estimated_fee=3.61,
        estimated_profit=7.88,
        estimated_margin_pct=0.3153,
        supplier_profit_status=SupplierProfitStatus.VERIFIED_PROFITABLE,
        status=CandidateStatus.APPROVED_FOR_LISTING,
        notes="Approved by merchant review committee",
    )


@pytest.fixture
def unapproved_candidate():
    return ProductCandidate(
        candidate_id="CAND-NEW-01",
        sku="SKU-UNAPP-01",
        title="Unapproved Candidate Item",
        supplier_id="WHOLESALE-02",
        target_platform=Platform.EBAY,
        supplier_cost=15.00,
        target_price=30.00,
        status=CandidateStatus.NEW,
    )


def test_convert_candidate_to_draft_includes_all_required_fields(approved_candidate):
    draft = create_ebay_draft(approved_candidate)

    # 1. title
    assert draft.title == "Matte Black 20oz Insulated Tumbler"

    # 2. SKU
    assert draft.sku == "SKU-TUMBLER-BLK"
    assert draft.SKU == "SKU-TUMBLER-BLK"

    # 3. price
    assert draft.price == 24.99

    # 4. quantity
    assert draft.quantity == 1

    # 5. description
    assert len(draft.description) > 0
    assert "SKU-TUMBLER-BLK" in draft.description

    # 6. category placeholder
    assert "Placeholder" in draft.category_placeholder or "Category" in draft.category_placeholder
    assert draft.category == draft.category_placeholder

    # 7. shipping placeholder
    assert "Shipping" in draft.shipping_placeholder
    assert draft.shipping == draft.shipping_placeholder

    # 8. supplier reference
    assert draft.supplier_reference == "WHOLESALE-DIRECT-01"

    # 9. expected profit
    assert draft.expected_profit == 7.88

    # 10. expected margin
    assert draft.expected_margin == 0.3153

    # Default initial human-review status
    assert draft.status == DraftReviewStatus.DRAFT_CREATED
    assert draft.human_approval_required is True
    assert draft.reviewed_by is None


def test_cannot_convert_unapproved_candidate():
    unapproved = ProductCandidate(
        candidate_id="CAND-VERIFIED-01",
        sku="SKU-VER-01",
        title="Verified but not yet approved candidate",
        supplier_id="WHOLESALE-01",
        supplier_cost=10.0,
        target_price=20.0,
        status=CandidateStatus.VERIFIED,
    )

    with pytest.raises(ValueError) as exc_info:
        create_ebay_draft(unapproved)
    assert "APPROVED_FOR_LISTING" in str(exc_info.value)


def test_cannot_convert_new_or_rejected_candidates():
    for invalid_status in (CandidateStatus.NEW, CandidateStatus.REVIEW, CandidateStatus.REJECTED):
        candidate = ProductCandidate(
            candidate_id="CAND-TEST",
            sku="SKU-TEST",
            title="Candidate",
            supplier_id="SUP-1",
            supplier_cost=10.0,
            target_price=20.0,
            status=invalid_status,
        )
        with pytest.raises(ValueError):
            create_ebay_draft(candidate)


def test_cannot_create_draft_without_verified_profitable_supplier(approved_candidate):
    for status in (
        SupplierProfitStatus.NEEDS_SUPPLIER_DATA,
        SupplierProfitStatus.VERIFIED_LOW_MARGIN,
        SupplierProfitStatus.SUPPLIER_REJECTED,
    ):
        candidate = approved_candidate.model_copy(update={"supplier_profit_status": status})
        with pytest.raises(ValueError, match="VERIFIED_PROFITABLE"):
            create_ebay_draft(candidate)


def test_human_review_status_lifecycle_happy_path(tmp_path, approved_candidate):
    db_path = tmp_path / "test_lifecycle.db"
    queue = CandidateQueue(db_path=str(db_path))

    # Save candidate in queue
    queue.db.save_candidate(approved_candidate)

    # 1. DRAFT_CREATED
    draft = queue.create_ebay_draft(approved_candidate.candidate_id)
    assert draft.status == DraftReviewStatus.DRAFT_CREATED
    assert draft.reviewed_by is None

    # 2. READY_FOR_REVIEW
    ready_draft = queue.submit_draft_for_review(draft.draft_id)
    assert ready_draft.status == DraftReviewStatus.READY_FOR_REVIEW

    # 3. APPROVED_TO_PUBLISH (with human reviewer ID)
    approved_draft = queue.approve_draft_to_publish(draft.draft_id, reviewer="reviewer_sarah")
    assert approved_draft.status == DraftReviewStatus.APPROVED_TO_PUBLISH
    assert approved_draft.reviewed_by == "reviewer_sarah"
    assert approved_draft.reviewed_at is not None


def test_human_review_rejection_from_draft_created(tmp_path, approved_candidate):
    queue = CandidateQueue(db_path=str(tmp_path / "test_rej1.db"))
    queue.db.save_candidate(approved_candidate)

    draft = queue.create_ebay_draft(approved_candidate.candidate_id)
    rejected = queue.reject_draft(draft.draft_id, reason="Title violates naming policy")
    assert rejected.status == DraftReviewStatus.REJECTED
    assert rejected.rejection_reason == "Title violates naming policy"


def test_human_review_rejection_from_ready_for_review(tmp_path, approved_candidate):
    queue = CandidateQueue(db_path=str(tmp_path / "test_rej2.db"))
    queue.db.save_candidate(approved_candidate)

    draft = queue.create_ebay_draft(approved_candidate.candidate_id)
    queue.submit_draft_for_review(draft.draft_id)
    rejected = queue.reject_draft(draft.draft_id, reason="Category taxonomy needs re-classification")
    assert rejected.status == DraftReviewStatus.REJECTED
    assert rejected.rejection_reason == "Category taxonomy needs re-classification"


def test_invalid_draft_status_transitions_raise_error(tmp_path, approved_candidate):
    queue = CandidateQueue(db_path=str(tmp_path / "test_inv.db"))
    queue.db.save_candidate(approved_candidate)

    draft = queue.create_ebay_draft(approved_candidate.candidate_id)

    # Cannot skip READY_FOR_REVIEW to jump straight to APPROVED_TO_PUBLISH
    with pytest.raises(InvalidDraftStatusTransitionError):
        queue.transition_draft(
            draft.draft_id,
            DraftReviewStatus.APPROVED_TO_PUBLISH,
            reviewed_by="admin",
        )

    # Advance to READY_FOR_REVIEW then APPROVED_TO_PUBLISH
    queue.submit_draft_for_review(draft.draft_id)
    queue.approve_draft_to_publish(draft.draft_id, reviewer="admin")

    # APPROVED_TO_PUBLISH cannot transition backwards to DRAFT_CREATED
    with pytest.raises(InvalidDraftStatusTransitionError):
        queue.transition_draft(draft.draft_id, DraftReviewStatus.DRAFT_CREATED)


def test_approving_without_reviewer_identifier_raises_error(tmp_path, approved_candidate):
    queue = CandidateQueue(db_path=str(tmp_path / "test_no_rev.db"))
    queue.db.save_candidate(approved_candidate)

    draft = queue.create_ebay_draft(approved_candidate.candidate_id)
    queue.submit_draft_for_review(draft.draft_id)

    with pytest.raises(ValueError):
        queue.approve_draft_to_publish(draft.draft_id, reviewer="")

    with pytest.raises(ValueError):
        queue.transition_draft(
            draft.draft_id,
            DraftReviewStatus.APPROVED_TO_PUBLISH,
            reviewed_by=None,
        )


def test_sqlite_persistence_and_querying_drafts(tmp_path, approved_candidate):
    db = CommerceDatabase(str(tmp_path / "drafts.db"))
    db.save_candidate(approved_candidate)

    draft = EBayListingDraft.from_candidate(approved_candidate)
    saved = db.save_draft(draft)
    assert saved.draft_id == f"DRAFT-EBAY-{approved_candidate.sku}"

    # Query by draft_id
    loaded = db.get_draft(saved.draft_id)
    assert loaded is not None
    assert loaded.title == approved_candidate.title
    assert loaded.expected_profit == approved_candidate.estimated_profit
    assert loaded.status == DraftReviewStatus.DRAFT_CREATED

    # Query by candidate_id
    by_candidate = db.get_draft_by_candidate_id(approved_candidate.candidate_id)
    assert by_candidate is not None
    assert by_candidate.draft_id == saved.draft_id

    # Filter by status
    drafts = db.list_drafts(status=DraftReviewStatus.DRAFT_CREATED)
    assert len(drafts) == 1

    # Update status
    db.update_draft_status(
        draft_id=saved.draft_id,
        new_status=DraftReviewStatus.READY_FOR_REVIEW,
    )
    updated = db.get_draft(saved.draft_id)
    assert updated.status == DraftReviewStatus.READY_FOR_REVIEW


def test_ebay_adapter_with_listing_draft(approved_candidate):
    adapter = EBayAdapter()
    draft = create_ebay_draft(approved_candidate)

    # 1. Unapproved draft produces PENDING_APPROVAL listing
    listing = adapter.create_listing(draft)
    assert listing.status == ListingStatus.PENDING_APPROVAL
    assert listing.human_approved is False

    # Attempting to publish an unapproved listing strictly raises PermissionError
    with pytest.raises(PermissionError):
        adapter.publish_listing(listing)

    # 2. Approved draft produces APPROVED listing
    draft.status = DraftReviewStatus.APPROVED_TO_PUBLISH
    draft.reviewed_by = "human_operator_42"
    approved_listing = adapter.create_listing(draft)
    assert approved_listing.status == ListingStatus.APPROVED
    assert approved_listing.human_approved is True
    assert approved_listing.approved_by == "human_operator_42"


def test_draft_count_by_status(tmp_path, approved_candidate):
    queue = CandidateQueue(db_path=str(tmp_path / "counts.db"))
    queue.db.save_candidate(approved_candidate)

    draft = queue.create_ebay_draft(approved_candidate.candidate_id)
    counts = queue.count_drafts_by_status()

    assert counts["DRAFT_CREATED"] == 1
    assert counts["READY_FOR_REVIEW"] == 0
    assert counts["APPROVED_TO_PUBLISH"] == 0
    assert counts["REJECTED"] == 0

    queue.submit_draft_for_review(draft.draft_id)
    counts = queue.count_drafts_by_status()
    assert counts["DRAFT_CREATED"] == 0
    assert counts["READY_FOR_REVIEW"] == 1
