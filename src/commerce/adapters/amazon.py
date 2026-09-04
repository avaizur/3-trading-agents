from typing import Optional

from src.commerce.schemas import (
    Listing,
    Platform,
    PlatformStatus,
    SellerListingDraft,
)


class PlatformDisabledError(RuntimeError):
    """Raised when an operation is attempted on a disabled/on-hold platform."""
    pass


class AmazonAdapter:
    """
    Amazon Adapter placeholder.
    Explicitly kept disabled/on hold per Phase 1 architectural roadmap.
    """

    def __init__(self):
        self.platform = Platform.AMAZON
        self.status = PlatformStatus.ON_HOLD
        self.is_enabled = False

    def create_listing(self, draft: SellerListingDraft) -> Listing:
        raise PlatformDisabledError(
            "Amazon adapter is disabled/on hold. eBay is the only active platform in Phase 1."
        )

    def publish_listing(self, listing: Listing) -> dict:
        raise PlatformDisabledError(
            "Amazon adapter is disabled/on hold. eBay is the only active platform in Phase 1."
        )

    def estimate_fees(self, sale_price: float) -> float:
        raise PlatformDisabledError(
            "Amazon adapter is disabled/on hold. Cannot estimate fees."
        )

    def test_connection(self) -> dict:
        return {
            "platform": self.platform.value,
            "status": self.status.value,
            "is_enabled": self.is_enabled,
            "message": "Amazon adapter is on hold and disabled in Phase 1",
        }
