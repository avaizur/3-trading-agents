from typing import Optional

from src.commerce.schemas import (
    Listing,
    ListingApprovalStatus,
    ListingStatus,
    Platform,
    PlatformStatus,
    SellerListingDraft,
)


class EBayAdapter:
    """
    eBay Adapter: Active first platform.
    Enforces human-approved listing constraint and offline placeholder operation (no external APIs yet).
    """

    def __init__(self):
        self.platform = Platform.EBAY
        self.status = PlatformStatus.ACTIVE
        self.is_enabled = True

    def create_listing(self, draft: SellerListingDraft) -> Listing:
        """
        Creates a platform listing record from a seller draft.
        If draft is not human-approved, listing is marked PENDING_APPROVAL and human_approved=False.
        """
        if (
            draft.approval_status == ListingApprovalStatus.APPROVED
            and draft.approved_by is not None
        ):
            return Listing(
                listing_id=f"EBAY-DRAFT-{draft.sku}",
                platform=Platform.EBAY,
                sku=draft.sku,
                title=draft.title,
                price=draft.proposed_price,
                status=ListingStatus.APPROVED,
                human_approved=True,
                approved_by=draft.approved_by,
            )

        return Listing(
            listing_id=f"EBAY-DRAFT-{draft.sku}",
            platform=Platform.EBAY,
            sku=draft.sku,
            title=draft.title,
            price=draft.proposed_price,
            status=ListingStatus.PENDING_APPROVAL,
            human_approved=False,
            approved_by=None,
        )

    def publish_listing(self, listing: Listing) -> dict:
        """
        Publishes listing to eBay.
        Strictly blocks publishing if human approval is missing.
        """
        if not listing.human_approved:
            raise PermissionError(
                "Human approval is required before publishing any listing to eBay."
            )

        listing.status = ListingStatus.ACTIVE
        listing.listing_id = f"EBAY-{listing.sku}"

        return {
            "listing_id": listing.listing_id,
            "platform": Platform.EBAY.value,
            "status": ListingStatus.ACTIVE.value,
            "message": "Listing published successfully (placeholder mode: no external APIs invoked)",
        }

    def estimate_fees(
        self,
        sale_price: float,
        final_value_rate: float = 0.1325,
        per_order_fee: float = 0.30,
    ) -> float:
        """
        Deterministic fee estimator for standard eBay categories:
        Final value fee ~13.25% + $0.30 fixed per-order fee.
        """
        if sale_price <= 0:
            return 0.0
        return round((sale_price * final_value_rate) + per_order_fee, 2)

    def test_connection(self) -> dict:
        """Adapter status report."""
        return {
            "platform": self.platform.value,
            "status": self.status.value,
            "is_enabled": self.is_enabled,
            "mode": "offline_placeholder",
            "message": "eBay active first platform placeholder (no external APIs yet)",
        }
