import pytest

from src.commerce.adapters.amazon import AmazonAdapter, PlatformDisabledError
from src.commerce.adapters.ebay import EBayAdapter
from src.commerce.adapters.supplier_base import BaseSupplierAdapter
from src.commerce.schemas import (
    Listing,
    ListingApprovalStatus,
    ListingStatus,
    Platform,
    PlatformStatus,
    SellerListingDraft,
    SupplierOrderStatus,
    SupplierProduct,
    SupplierType,
)


class DummySupplierAdapter(BaseSupplierAdapter):
    """Concrete mock adapter for testing BaseSupplierAdapter logic."""

    def get_product(self, sku: str):
        if sku == "SKU-FOUND":
            return SupplierProduct(
                supplier_id=self.supplier_id,
                sku=sku,
                title="Mock Item",
                supplier_type=SupplierType.WHOLESALE,
                cost=20.0,
                shipping_cost=5.0,
                inventory_count=100,
                allows_reselling=True,
            )
        return None

    def check_inventory(self, sku: str) -> int:
        return 100 if sku == "SKU-FOUND" else 0


def test_supplier_base_adapter_manual_order():
    adapter = DummySupplierAdapter(supplier_id="SUP-TEST", supplier_name="Test Wholesale Co")
    order = adapter.create_manual_order(
        sku="SKU-FOUND",
        quantity=5,
        cost_per_unit=20.0,
        shipping_cost=10.0,
        ordered_by="operator_dan",
        notes="First batch manual order",
    )

    assert order.supplier_id == "SUP-TEST"
    assert order.sku == "SKU-FOUND"
    assert order.quantity == 5
    assert order.total_cost == 110.0  # (20 * 5) + 10
    assert order.is_manual is True
    assert order.status == SupplierOrderStatus.MANUAL_PENDING
    assert order.ordered_by == "operator_dan"


def test_supplier_base_adapter_auto_fulfill_blocked():
    adapter = DummySupplierAdapter(supplier_id="SUP-TEST", supplier_name="Test Wholesale Co")
    with pytest.raises(NotImplementedError) as excinfo:
        adapter.auto_fulfill_order(sku="SKU-FOUND", quantity=5)
    assert "manual supplier ordering only" in str(excinfo.value)


def test_supplier_base_adapter_connection():
    adapter = DummySupplierAdapter(supplier_id="SUP-TEST", supplier_name="Test Wholesale Co")
    status = adapter.test_connection()
    assert status["status"] == "HEALTHY"
    assert status["mode"] == "offline_placeholder"


def test_ebay_adapter_is_active_platform():
    ebay = EBayAdapter()
    assert ebay.platform == Platform.EBAY
    assert ebay.status == PlatformStatus.ACTIVE
    assert ebay.is_enabled is True

    conn = ebay.test_connection()
    assert conn["status"] == "ACTIVE"
    assert conn["is_enabled"] is True


def test_ebay_adapter_requires_human_approval_for_publishing():
    ebay = EBayAdapter()

    # Draft without human approval
    unapproved_draft = SellerListingDraft(
        agent_name="seller_a",
        sku="SKU-EBAY-1",
        title="Ceramic Mug",
        description="A nice mug",
        proposed_price=19.99,
        approval_status=ListingApprovalStatus.PENDING_APPROVAL,
    )
    listing = ebay.create_listing(unapproved_draft)
    assert listing.human_approved is False
    assert listing.status == ListingStatus.PENDING_APPROVAL

    # Publishing unapproved listing must fail
    with pytest.raises(PermissionError) as excinfo:
        ebay.publish_listing(listing)
    assert "Human approval is required" in str(excinfo.value)


def test_ebay_adapter_publishes_approved_listing():
    ebay = EBayAdapter()

    approved_draft = SellerListingDraft(
        agent_name="seller_b",
        sku="SKU-EBAY-2",
        title="Ceramic Mug Set",
        description="A nice set of mugs",
        proposed_price=39.99,
        approval_status=ListingApprovalStatus.APPROVED,
        approved_by="reviewer_alice",
    )
    listing = ebay.create_listing(approved_draft)
    assert listing.human_approved is True
    assert listing.status == ListingStatus.APPROVED

    # Now publishing succeeds
    result = ebay.publish_listing(listing)
    assert result["status"] == "ACTIVE"
    assert result["listing_id"] == "EBAY-SKU-EBAY-2"
    assert listing.status == ListingStatus.ACTIVE


def test_ebay_adapter_fee_estimation():
    ebay = EBayAdapter()
    # 100.0 * 0.1325 + 0.30 = 13.25 + 0.30 = 13.55
    fee = ebay.estimate_fees(100.0)
    assert fee == 13.55


def test_amazon_adapter_is_disabled_and_on_hold():
    amazon = AmazonAdapter()
    assert amazon.platform == Platform.AMAZON
    assert amazon.status == PlatformStatus.ON_HOLD
    assert amazon.is_enabled is False

    conn = amazon.test_connection()
    assert conn["status"] == "ON_HOLD"
    assert conn["is_enabled"] is False


def test_amazon_adapter_operations_raise_disabled_error():
    amazon = AmazonAdapter()
    draft = SellerListingDraft(
        agent_name="seller_a",
        sku="SKU-AMZ-1",
        title="Amazon Draft",
        description="Desc",
        proposed_price=24.99,
    )
    listing = Listing(
        sku="SKU-AMZ-1",
        platform=Platform.AMAZON,
        title="Amazon Item",
        price=24.99,
    )

    with pytest.raises(PlatformDisabledError):
        amazon.create_listing(draft)

    with pytest.raises(PlatformDisabledError):
        amazon.publish_listing(listing)

    with pytest.raises(PlatformDisabledError):
        amazon.estimate_fees(24.99)
