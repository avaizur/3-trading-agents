from typing import Optional

from src.commerce.schemas import EBayListingDraft, ProductCandidate


def run():
    return "Seller A not connected yet"


def create_ebay_draft(
    candidate: ProductCandidate,
    quantity: int = 1,
    description: Optional[str] = None,
    category: Optional[str] = None,
    shipping: Optional[str] = None,
) -> EBayListingDraft:
    """
    Seller A (eBay Agent) conversion function:
    Converts a candidate in APPROVED_FOR_LISTING status into an eBay listing draft.
    """
    return EBayListingDraft.from_candidate(
        candidate=candidate,
        quantity=quantity,
        description=description,
        category=category,
        shipping=shipping,
    )
