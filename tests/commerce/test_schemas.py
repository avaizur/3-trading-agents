from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from src.commerce.schemas import (
    CommerceCriticRecommendation,
    CommerceCriticReview,
    Listing,
    ListingApprovalStatus,
    ListingStatus,
    Platform,
    PlatformStatus,
    ProductScoutOpportunity,
    ProfitCalculationInput,
    ProfitDecision,
    SellerListingDraft,
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
