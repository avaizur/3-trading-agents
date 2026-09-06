"""Create and print one local eBay listing draft from the commerce database."""

import argparse
import json
from typing import Sequence

from src.commerce.queue import CandidateQueue
from src.commerce.schemas import (
    CandidateStatus,
    Platform,
    ProductCandidate,
    SupplierProfitStatus,
)


def _select_candidate(
    queue: CandidateQueue, candidate_id: str | None = None
) -> ProductCandidate:
    candidates = (
        [queue.get_candidate(candidate_id)]
        if candidate_id is not None
        else queue.get_queue(limit=10_000)
    )
    candidates = [candidate for candidate in candidates if candidate is not None]
    eligible = [
        candidate
        for candidate in candidates
        if candidate.supplier_profit_status
        is SupplierProfitStatus.VERIFIED_PROFITABLE
        and candidate.status is CandidateStatus.APPROVED_FOR_LISTING
        and candidate.target_platform is Platform.EBAY
    ]
    if eligible:
        return eligible[0]

    target = f" '{candidate_id}'" if candidate_id else ""
    raise ValueError(
        f"No eligible candidate{target}: an eBay draft requires "
        "target platform EBAY, VERIFIED_PROFITABLE supplier economics, and "
        "APPROVED_FOR_LISTING status."
    )


def _ebay_item_id(candidate_id: str) -> str:
    return candidate_id.removeprefix("CAND-EBAY-")


def create_listing_draft(
    db_path: str = "data/commerce.db",
    *,
    candidate_id: str | None = None,
    quantity: int = 1,
) -> dict:
    """Select an eligible local candidate, persist its draft, and return output data."""
    queue = CandidateQueue(db_path=db_path)
    candidate = _select_candidate(queue, candidate_id)
    draft = queue.create_ebay_draft(candidate.candidate_id, quantity=quantity)

    supplier_name = candidate.supplier_id
    matches = queue.db.get_manual_supplier_matches(
        _ebay_item_id(candidate.candidate_id)
    )
    if matches and matches[-1].get("supplier_name"):
        supplier_name = matches[-1]["supplier_name"]

    return {
        "ebay_item_or_candidate_id": _ebay_item_id(candidate.candidate_id),
        "title": draft.title,
        "supplier_name": supplier_name,
        "supplier_sku": draft.sku,
        "sale_price": draft.price,
        "quantity": draft.quantity,
        "description": draft.description,
        "category_placeholder": draft.category_placeholder,
        "shipping_placeholder": draft.shipping_placeholder,
        "expected_profit": draft.expected_profit,
        "expected_margin": f"{draft.expected_margin:.2%}",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/commerce.db", help="SQLite database path")
    parser.add_argument("--candidate-id", help="Specific commerce candidate ID")
    parser.add_argument("--quantity", type=int, default=1, help="Draft quantity")
    args = parser.parse_args(argv)
    try:
        payload = create_listing_draft(
            args.db,
            candidate_id=args.candidate_id,
            quantity=args.quantity,
        )
    except (KeyError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
