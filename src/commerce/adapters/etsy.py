from src.commerce.adapters.marketplace_base import BaseMarketplaceAdapter
from src.commerce.schemas import (
    Listing,
    Platform,
    PlatformStatus,
    SellerListingDraft,
)


class EtsyAdapter(BaseMarketplaceAdapter):
    """
    Etsy Open API onboarding adapter.

    Disabled until shop OAuth authorization, taxonomy and marketplace
    validation are configured.
    """

    def __init__(self):
        self.platform = Platform.ETSY
        self.status = PlatformStatus.ON_HOLD
        self.is_enabled = False

    def create_listing(self, draft: SellerListingDraft) -> Listing:
        self._require_enabled()
        return self._listing_from_draft(draft)

    def publish_listing(self, listing: Listing) -> dict:
        self._require_enabled()
        self.require_human_approval(listing)
        raise NotImplementedError(
            "Etsy API publication is not configured yet."
        )

    def estimate_fees(self, sale_price: float) -> float:
        self._require_enabled()
        raise NotImplementedError(
            "Etsy fees require live marketplace configuration."
        )

    def test_connection(self) -> dict:
        result = super().test_connection()
        result["message"] = (
            "Etsy adapter ready for future seller OAuth onboarding."
        )
        return result
