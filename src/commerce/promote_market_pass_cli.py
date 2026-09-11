"""Move market-validation PASS supplier products into human REVIEW."""

import argparse
from typing import Sequence

from src.commerce.database import CommerceDatabase
from src.commerce.queue import CandidateQueue
from src.commerce.schemas import (
    CandidateStatus,
    MarketValidationStatus,
    Platform,
    ProductCandidate,
    ProductLane,
    SupplierProfitStatus,
)


def _candidate_id(sku: str) -> str:
    return f"CAND-EBAY-{sku}"


def _category(lane: ProductLane, sku: str) -> str:
    if sku.startswith("PET-"):
        return "Pet Supplies"
    if lane is ProductLane.SEASONAL:
        return "Home, Furniture & DIY > Seasonal Decorations"
    return "General Merchandise > Default Category"


def promote_market_pass_products(
    db_path: str = "data/commerce.db",
) -> list[ProductCandidate]:
    db = CommerceDatabase(db_path)
    queue = CandidateQueue(db=db)
    promoted = []
    for product in db.list_supplier_backed_products():
        if product.market_validation_status is not MarketValidationStatus.PASS:
            continue
        candidate_id = _candidate_id(product.supplier_sku)
        candidate = queue.get_candidate(candidate_id)
        if candidate is None:
            candidate = queue.enqueue(ProductCandidate(
                candidate_id=candidate_id,
                sku=product.supplier_sku,
                title=product.product_name,
                category=_category(product.lane, product.supplier_sku),
                supplier_id=product.supplier_name,
                target_platform=Platform.EBAY,
                supplier_cost=product.supplier_cost,
                target_price=product.market_price,
                shipping_cost=0.0,
                estimated_fee=product.platform_fees,
                estimated_profit=product.expected_profit,
                estimated_margin_pct=product.expected_margin,
                supplier_profit_status=SupplierProfitStatus.VERIFIED_PROFITABLE,
                notes=f"Market validation PASS; lane {product.lane.value}.",
            ))
        if candidate.status is CandidateStatus.NEW:
            candidate = queue.transition(candidate_id, CandidateStatus.VERIFIED)
        if candidate.status is CandidateStatus.VERIFIED:
            candidate = queue.submit_for_review(
                candidate_id,
                notes=f"Market validation PASS; lane {product.lane.value}; awaiting human approval.",
            )
        if candidate.status in {
            CandidateStatus.REVIEW, CandidateStatus.APPROVED_FOR_LISTING,
        }:
            promoted.append(candidate)
    return promoted


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/commerce.db", help="SQLite database path")
    args = parser.parse_args(argv)
    try:
        candidates = promote_market_pass_products(args.db)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    for candidate in candidates:
        print(f"{candidate.sku}: {candidate.status.value} | {candidate.candidate_id}")
    print(f"Moved/retained {len(candidates)} PASS products in review workflow.")
    print("No products were approved or published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
