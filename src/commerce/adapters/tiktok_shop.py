from src.commerce.adapters.marketplace_base import BaseMarketplaceAdapter
from src.commerce.schemas import (
    Listing,
    Platform,
    PlatformStatus,
    SellerListingDraft,
)


class TikTokShopAdapter(BaseMarketplaceAdapter):
    """
    TikTok Shop onboarding adapter.

    Disabled until the Avaiizur TikTok Shop authorizes our own application
    and its credentials are stored securely in AWS.
    """

    def __init__(self):
        self.platform = Platform.TIKTOK_SHOP
        self.status = PlatformStatus.ON_HOLD
        self.is_enabled = False

    def create_listing(self, draft: SellerListingDraft) -> Listing:
        self._require_enabled()
        return self._listing_from_draft(draft)

    def publish_listing(self, listing: Listing) -> dict:
        self._require_enabled()
        self.require_human_approval(listing)
        raise NotImplementedError(
            "TikTok Shop API publication is not configured yet."
        )

    def estimate_fees(self, sale_price: float) -> float:
        self._require_enabled()
        raise NotImplementedError(
            "TikTok Shop fees require live marketplace configuration."
        )

    def test_connection(self) -> dict:
        result = super().test_connection()
        result["message"] = (
            "TikTok Shop adapter ready for seller-app authorization."
        )
        return result
