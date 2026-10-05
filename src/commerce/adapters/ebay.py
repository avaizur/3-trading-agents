from typing import Union

from src.commerce.adapters.marketplace_base import BaseMarketplaceAdapter
from src.commerce.schemas import (
    DraftReviewStatus,
    EBayListingDraft,
    Listing,
    ListingApprovalStatus,
    ListingStatus,
    Platform,
    PlatformStatus,
    SellerListingDraft,
)


class EBayAdapter(BaseMarketplaceAdapter):
    """
    eBay marketplace adapter.

    This adapter preserves the existing offline/domain behaviour while
    conforming to the shared marketplace interface.

    Real eBay Inventory API publication remains handled by the production
    eBay inventory service.
    """

    def __init__(self):
        self.platform = Platform.EBAY
        self.status = PlatformStatus.ACTIVE
        self.is_enabled = True

    def create_listing(
        self,
        draft: Union[SellerListingDraft, EBayListingDraft],
    ) -> Listing:
        self._require_enabled()

        if isinstance(draft, EBayListingDraft):
            is_approved = (
                draft.status == DraftReviewStatus.APPROVED_TO_PUBLISH
                and draft.reviewed_by is not None
            )

            return Listing(
                listing_id=f"EBAY-DRAFT-{draft.sku}",
                platform=Platform.EBAY,
                sku=draft.sku,
                title=draft.title,
                price=draft.price,
                quantity=draft.quantity,
                status=(
                    ListingStatus.APPROVED
                    if is_approved
                    else ListingStatus.PENDING_APPROVAL
                ),
                human_approved=is_approved,
                approved_by=draft.reviewed_by if is_approved else None,
            )

        is_approved = (
            draft.approval_status == ListingApprovalStatus.APPROVED
            and draft.approved_by is not None
        )

        return Listing(
            listing_id=f"EBAY-DRAFT-{draft.sku}",
            platform=Platform.EBAY,
            sku=draft.sku,
            title=draft.title,
            price=draft.proposed_price,
            quantity=1,
            status=(
                ListingStatus.APPROVED
                if is_approved
                else ListingStatus.PENDING_APPROVAL
            ),
            human_approved=is_approved,
            approved_by=draft.approved_by if is_approved else None,
        )

    def publish_listing(self, listing: Listing) -> dict:
        self._require_enabled()
        self.require_human_approval(listing)

        listing.status = ListingStatus.ACTIVE
        listing.listing_id = f"EBAY-{listing.sku}"

        return {
            "listing_id": listing.listing_id,
            "platform": Platform.EBAY.value,
            "status": ListingStatus.ACTIVE.value,
            "message": (
                "Listing approved in adapter domain layer. "
                "Production API publication is handled by the "
                "eBay inventory service."
            ),
        }

    def estimate_fees(
        self,
        sale_price: float,
        final_value_rate: float = 0.1325,
        per_order_fee: float = 0.30,
    ) -> float:
        if sale_price <= 0:
            return 0.0

        return round(
            (sale_price * final_value_rate) + per_order_fee,
            2,
        )

    def test_connection(self) -> dict:
        result = super().test_connection()
        result["mode"] = "production_capable"
        result["message"] = (
            "eBay adapter active. Real API operations are handled "
            "by dedicated eBay production services."
        )
        return result
