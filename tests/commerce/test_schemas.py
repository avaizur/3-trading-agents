from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from src.commerce.schemas import (
    CandidateStatus,
    CommerceCriticRecommendation,
    CommerceCriticReview,
    DraftReviewStatus,
    EBayListingDraft,
    Listing,
    ListingApprovalStatus,
    ListingStatus,
    Platform,
    PlatformStatus,
    ProductCandidate,
    ProductScoutOpportunity,
    ProfitCalculationInput,
    ProfitDecision,
    SellerListingDraft,
    SupplierCheckRecord,
    SupplierOrder,
    SupplierOrderStatus,
    SupplierProduct,
    SupplierType,
)


def test_supplier_product_valid():
    product = SupplierProduct(
        supplier_id="SUP-001",
        sku="SKU-100",
        title="Wholesale Stainless Steel Tumbler",
        supplier_type=SupplierType.WHOLESALE,
        cost=12.50,
        shipping_cost=2.50,
        inventory_count=500,
        lead_time_days=3,
        allows_reselling=True,
    )
    assert product.sku == "SKU-100"
    assert product.cost == 12.50
    assert product.supplier_type == SupplierType.WHOLESALE


def test_supplier_product_invalid_cost():
    with pytest.raises(ValidationError):
        SupplierProduct(
            supplier_id="SUP-001",
            sku="SKU-100",
            title="Invalid Product",
            supplier_type=SupplierType.WHOLESALE,
            cost=-5.0,  # Must be > 0
        )


def test_profit_calculation_input_normalizes_percent():
    p1 = ProfitCalculationInput(
        supplier_cost=20.0,
        shipping=5.0,
        platform_fee=4.0,
        return_buffer=1.0,
        sale_price=40.0,
        min_margin_pct=25.0,  # Supplied as 25%
    )
    assert p1.min_margin_pct == 0.25

    p2 = ProfitCalculationInput(
        supplier_cost=20.0,
        shipping=5.0,
        platform_fee=4.0,
        return_buffer=1.0,
        sale_price=40.0,
        min_margin_pct=0.20,  # Supplied as 0.20
    )
    assert p2.min_margin_pct == 0.20


def test_seller_listing_draft_requires_human_approval():
    # Draft should default to PENDING_APPROVAL and human_approval_required=True
    draft = SellerListingDraft(
        agent_name="seller_a",
        sku="SKU-100",
        title="Insulated Tumbler 20oz",
        description="Great quality tumbler",
        proposed_price=29.99,
    )
    assert draft.human_approval_required is True
    assert draft.approval_status == ListingApprovalStatus.PENDING_APPROVAL

    # Cannot disable human_approval_required
    with pytest.raises(ValidationError):
        SellerListingDraft(
            agent_name="seller_a",
            sku="SKU-100",
            title="Tumbler",
            description="Desc",
            proposed_price=29.99,
            human_approval_required=False,
        )


def test_seller_listing_approved_requires_reviewer():
    # Setting APPROVED without approved_by must fail
    with pytest.raises(ValidationError):
        SellerListingDraft(
            agent_name="seller_a",
            sku="SKU-100",
            title="Tumbler",
            description="Desc",
            proposed_price=29.99,
            approval_status=ListingApprovalStatus.APPROVED,
            approved_by=None,
        )

    # Valid approval
    draft = SellerListingDraft(
        agent_name="seller_a",
        sku="SKU-100",
        title="Tumbler",
        description="Desc",
        proposed_price=29.99,
        approval_status=ListingApprovalStatus.APPROVED,
        approved_by="human_operator_1",
    )
    assert draft.approved_by == "human_operator_1"


def test_supplier_order_enforces_manual():
    order = SupplierOrder(
        supplier_id="SUP-001",
        sku="SKU-100",
        quantity=10,
        cost_per_unit=12.50,
        shipping_cost=5.00,
        total_cost=130.00,
        is_manual=True,
    )
    assert order.is_manual is True
    assert order.status == SupplierOrderStatus.MANUAL_PENDING

    # Attempting automated order (is_manual=False) is rejected by schema validator
    with pytest.raises(ValidationError):
        SupplierOrder(
            supplier_id="SUP-001",
            sku="SKU-100",
            quantity=10,
            cost_per_unit=12.50,
            shipping_cost=5.00,
            total_cost=130.00,
            is_manual=False,
        )


def test_listing_model():
    listing = Listing(
        sku="SKU-100",
        platform=Platform.EBAY,
        title="Tumbler 20oz",
        price=29.99,
        status=ListingStatus.DRAFT,
        human_approved=False,
    )
    assert listing.platform == Platform.EBAY
    assert listing.human_approved is False


def test_critic_review_model():
    review = CommerceCriticReview(
        opportunity_id="OPP-001",
        recommendation=CommerceCriticRecommendation.CONTINUE,
        reason="Healthy margin and verified wholesale supplier",
        risk_flags=[],
    )
    assert review.recommendation == CommerceCriticRecommendation.CONTINUE


def test_supplier_product_negative_lead_time():
    with pytest.raises(ValidationError):
        SupplierProduct(
            supplier_id="SUP-001",
            sku="SKU-100",
            title="Invalid Product",
            supplier_type=SupplierType.WHOLESALE,
            cost=10.0,
            lead_time_days=-1,
        )


def test_candidate_status_enum_values():
    assert CandidateStatus.NEW.value == "NEW"
    assert CandidateStatus.VERIFIED.value == "VERIFIED"
    assert CandidateStatus.REVIEW.value == "REVIEW"
    assert CandidateStatus.REJECTED.value == "REJECTED"
    assert CandidateStatus.APPROVED_FOR_LISTING.value == "APPROVED_FOR_LISTING"


def test_product_candidate_validation():
    candidate = ProductCandidate(
        candidate_id="CAND-001",
        sku="SKU-001",
        title="Test Candidate",
        supplier_id="SUP-01",
        supplier_cost=15.0,
        target_price=30.0,
    )
    assert candidate.status == CandidateStatus.NEW
    assert candidate.target_platform == Platform.EBAY

    # Negative supplier cost raises ValidationError
    with pytest.raises(ValidationError):
        ProductCandidate(
            candidate_id="CAND-002",
            sku="SKU-002",
            title="Invalid Candidate",
            supplier_id="SUP-01",
            supplier_cost=-5.0,
            target_price=30.0,
        )


def test_supplier_check_record_schema():
    check = SupplierCheckRecord(
        candidate_id="CAND-001",
        supplier_id="SUP-WHOLESALE",
        sku="SKU-001",
        supplier_type=SupplierType.WHOLESALE,
        is_valid=True,
        retail_dropshipping_blocked=False,
        reason="Checks passed",
        passed_checks=["valid_cost"],
        warnings=[],
    )
    assert check.is_valid is True
    assert check.supplier_type == SupplierType.WHOLESALE
    assert check.retail_dropshipping_blocked is False


def test_draft_review_status_enum_values():
    assert DraftReviewStatus.DRAFT_CREATED.value == "DRAFT_CREATED"
    assert DraftReviewStatus.READY_FOR_REVIEW.value == "READY_FOR_REVIEW"
    assert DraftReviewStatus.APPROVED_TO_PUBLISH.value == "APPROVED_TO_PUBLISH"
    assert DraftReviewStatus.REJECTED.value == "REJECTED"


def test_ebay_listing_draft_validation_and_placeholders():
    draft = EBayListingDraft(
        draft_id="DRAFT-001",
        sku="SKU-TEST-01",
        title="Test Title",
        price=19.99,
        quantity=2,
        description="Detailed description",
        category_placeholder="Electronics > Audio",
        shipping_placeholder="Express Shipping",
        supplier_reference="SUP-1",
        expected_profit=5.0,
        expected_margin=0.25,
    )
    assert draft.category == "Electronics > Audio"
    assert draft.category_placeholder == "Electronics > Audio"
    assert draft.shipping == "Express Shipping"
    assert draft.shipping_placeholder == "Express Shipping"
    assert draft.SKU == "SKU-TEST-01"
    assert draft.status == DraftReviewStatus.DRAFT_CREATED

    # Human approval required cannot be False
    with pytest.raises(ValidationError):
        EBayListingDraft(
            draft_id="DRAFT-002",
            sku="SKU-TEST-02",
            title="Invalid",
            price=10.0,
            description="Desc",
            supplier_reference="SUP-1",
            expected_profit=2.0,
            expected_margin=0.20,
            human_approval_required=False,
        )

    # Approved status without reviewer raises ValidationError
    with pytest.raises(ValidationError):
        EBayListingDraft(
            draft_id="DRAFT-003",
            sku="SKU-TEST-03",
            title="Approved Without Reviewer",
            price=10.0,
            description="Desc",
            supplier_reference="SUP-1",
            expected_profit=2.0,
            expected_margin=0.20,
            status=DraftReviewStatus.APPROVED_TO_PUBLISH,
            reviewed_by=None,
        )
