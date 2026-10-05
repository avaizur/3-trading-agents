from abc import ABC, abstractmethod

from src.commerce.schemas import (
    Listing,
    ListingApprovalStatus,
    ListingStatus,
    Platform,
    PlatformStatus,
    SellerListingDraft,
)


class PlatformDisabledError(RuntimeError):
    """Raised when a marketplace has not yet been enabled."""


class BaseMarketplaceAdapter(ABC):
    """
    Common marketplace contract.

    Safety rules:
    - Human approval is always required before publication.
    - Disabled marketplaces cannot create or publish listings.
    - Marketplace-specific API logic belongs in the concrete adapter.
    """

    platform: Platform
    status: PlatformStatus
    is_enabled: bool

    def _require_enabled(self) -> None:
        if not self.is_enabled:
            raise PlatformDisabledError(
                f"{self.platform.value} marketplace adapter is not enabled."
            )

    def _listing_from_draft(
        self,
        draft: SellerListingDraft,
    ) -> Listing:
        is_approved = (
            draft.approval_status == ListingApprovalStatus.APPROVED
            and draft.approved_by is not None
        )

        return Listing(
            listing_id=f"{self.platform.value}-DRAFT-{draft.sku}",
            platform=self.platform,
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

    @staticmethod
    def require_human_approval(listing: Listing) -> None:
        if not listing.human_approved:
            raise PermissionError(
                "Human approval is required before publishing any marketplace listing."
            )

    @abstractmethod
    def create_listing(self, draft: SellerListingDraft) -> Listing:
        raise NotImplementedError

    @abstractmethod
    def publish_listing(self, listing: Listing) -> dict:
        raise NotImplementedError

    @abstractmethod
    def estimate_fees(self, sale_price: float) -> float:
        raise NotImplementedError

    def test_connection(self) -> dict:
        return {
            "platform": self.platform.value,
            "status": self.status.value,
            "is_enabled": self.is_enabled,
        }
