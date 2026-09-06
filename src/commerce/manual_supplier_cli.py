"""Interactive, local-only CLI for manual eBay supplier verification."""

import argparse
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Sequence

from pydantic import ValidationError

from src.commerce.database import CommerceDatabase
from src.commerce.market_research import MarketListing
from src.commerce.opportunity_scoring import OpportunityDecision, ScoredMarketOpportunity
from src.commerce.queue import CandidateQueue
from src.commerce.schemas import (
    CandidateStatus,
    SupplierCheckRecord,
    SupplierProduct,
    SupplierProfitStatus,
    SupplierType,
)
from src.commerce.supplier_matching import ManualSupplierInput, verify_manual_supplier_match


def _opportunity(raw: dict) -> ScoredMarketOpportunity:
    listing = dict(raw["listing"])
    listing["price"] = Decimal(str(listing["price"]))
    if listing.get("end_date"):
        listing["end_date"] = datetime.fromisoformat(listing["end_date"])
    values = dict(raw)
    values["listing"] = MarketListing(**listing)
    values["decision"] = OpportunityDecision(values["decision"])
    values["reasons"] = tuple(values.get("reasons", ()))
    opportunity = ScoredMarketOpportunity(**values)
    if opportunity.decision is not OpportunityDecision.SHORTLIST:
        raise ValueError("Candidate must have decision SHORTLIST.")
    return opportunity


def load_shortlist(path: str) -> list[ScoredMarketOpportunity]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else [data]
    if not rows:
        raise ValueError("Shortlist is empty.")
    return [_opportunity(row) for row in rows]


def _ask(prompt: str, convert: Callable = str, *, input_fn=input):
    while True:
        try:
            value = input_fn(prompt).strip()
            return convert(value)
        except (ValueError, TypeError) as exc:
            print(f"Invalid value: {exc}")


def _yes_no(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"y", "yes", "true", "1"}:
        return True
    if normalized in {"n", "no", "false", "0"}:
        return False
    raise ValueError("enter yes or no")


def _select(items: list[ScoredMarketOpportunity], input_fn=input):
    if len(items) == 1:
        return items[0]
    for index, item in enumerate(items, 1):
        print(f"{index}. {item.listing.item_id} | {item.listing.title} | "
              f"{item.listing.currency} {item.listing.price}")
    index = _ask("Select candidate number: ", int, input_fn=input_fn)
    if index < 1 or index > len(items):
        raise ValueError("Selection is outside the shortlist.")
    return items[index - 1]


def run(
    shortlist_path: str,
    db_path: str,
    *,
    input_fn=input,
    supplier_name: str | None = None,
    supplier_sku: str | None = None,
    supplier_cost: float | None = None,
    shipping_cost: float | None = None,
    stock_confirmed: int | None = None,
    direct_ship: bool | None = None,
    verification_status: str | None = None,
) -> int:
    opportunity = _select(load_shortlist(shortlist_path), input_fn)
    print(f"Selected: {opportunity.listing.item_id} | {opportunity.listing.title}")
    db = CommerceDatabase(db_path)
    candidate_id = f"CAND-EBAY-{opportunity.listing.item_id}"
    existing_candidate = db.get_candidate(candidate_id)
    is_verified_reverification = (
        existing_candidate is not None
        and existing_candidate.status == CandidateStatus.VERIFIED
    )
    persisted_supplier = None
    if (
        existing_candidate is not None
        and existing_candidate.supplier_profit_status
        is SupplierProfitStatus.VERIFIED_PROFITABLE
    ):
        matches = db.get_manual_supplier_matches(opportunity.listing.item_id)
        complete_matches = [
            match for match in matches
            if match["supplier_status"] == SupplierProfitStatus.VERIFIED_PROFITABLE.value
            and match["verification_status"] == "VERIFIED"
            and all(match[field] is not None for field in (
                "supplier_name", "sku", "cost", "shipping", "stock", "direct_ship",
            ))
        ]
        if complete_matches:
            persisted_supplier = complete_matches[-1]
            print("Loaded persisted supplier data for verified profitable candidate.")

    def supplied(explicit, persisted_key, prompt, convert=str):
        if explicit is not None:
            return explicit
        if persisted_supplier is not None:
            return persisted_supplier[persisted_key]
        return _ask(prompt, convert, input_fn=input_fn)

    try:
        supplier = ManualSupplierInput(
            name=supplied(supplier_name, "supplier_name", "Supplier name: "),
            sku=supplied(supplier_sku, "sku", "Supplier SKU: "),
            cost=supplied(supplier_cost, "cost", "Unit cost: ", float),
            shipping=supplied(shipping_cost, "shipping", "Shipping: ", float),
            stock=supplied(stock_confirmed, "stock", "Stock: ", int),
            direct_ship=supplied(
                direct_ship, "direct_ship", "Direct ship? [yes/no]: ", _yes_no,
            ),
            verification_status=(
                verification_status.upper() if verification_status is not None
                else persisted_supplier["verification_status"]
                if persisted_supplier is not None
                else _ask(
                    "Verification status [PENDING/VERIFIED/REJECTED]: ",
                    lambda value: value.upper(), input_fn=input_fn,
                )
            ),
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid supplier details: {exc}") from exc

    result = verify_manual_supplier_match(opportunity, supplier)
    profit = result.profit_decision.net_profit if result.profit_decision else None
    margin = result.profit_decision.margin_pct if result.profit_decision else None
    current = None
    if result.candidate is not None:
        if existing_candidate is not None:
            # Supplier verification must not rewind the separate human-review lifecycle.
            result.candidate.status = existing_candidate.status
            result.candidate.notes = existing_candidate.notes
            result.candidate.rejection_reason = existing_candidate.rejection_reason
        current = db.save_candidate(result.candidate)
        if (
            is_verified_reverification
            and result.status == SupplierProfitStatus.VERIFIED_PROFITABLE
        ):
            current = CandidateQueue(db=db).submit_for_review(
                candidate_id,
                notes=(
                    "Supplier and profit already verified; awaiting human listing "
                    "approval."
                ),
            )
    if result.candidate is not None and result.supplier_validation is not None:
        product = SupplierProduct(
            supplier_id=supplier.name, supplier_name=supplier.name, sku=supplier.sku,
            title=opportunity.listing.title,
            supplier_type=SupplierType.DIRECT if supplier.direct_ship else SupplierType.WHOLESALE,
            cost=supplier.cost, shipping_cost=supplier.shipping,
            inventory_count=supplier.stock, allows_reselling=True,
        )
        db.record_supplier_check(SupplierCheckRecord.from_validation_result(
            product, result.supplier_validation, result.candidate.candidate_id
        ))
    db.record_manual_supplier_match({
        "ebay_item_id": opportunity.listing.item_id,
        "supplier_name": supplier.name, "sku": supplier.sku, "cost": supplier.cost,
        "shipping": supplier.shipping, "stock": supplier.stock,
        "direct_ship": supplier.direct_ship,
        "verification_status": supplier.verification_status.value,
        "supplier_status": result.status.value,
        "expected_profit": profit, "expected_margin": margin,
        "final_outcome": result.reason,
    })

    print(f"Supplier status: {result.status.value}")
    print(f"Expected profit: {'N/A' if profit is None else f'{profit:.2f}'}")
    print(f"Margin: {'N/A' if margin is None else f'{margin:.2%}'}")
    print(f"Final outcome: {result.reason}")
    if current is not None and current.status is not CandidateStatus.APPROVED_FOR_LISTING:
        print(
            f"Candidate status: {current.status.value}; not APPROVED_FOR_LISTING "
            "because human approval is still required."
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shortlist", help="JSON file containing one or more scored eBay opportunities")
    parser.add_argument("--db", default="data/commerce.db", help="SQLite database path")
    parser.add_argument("--supplier-name", help="Supplier name")
    parser.add_argument("--supplier-sku", help="Supplier SKU")
    parser.add_argument("--supplier-cost", type=float, help="Supplier unit cost")
    parser.add_argument("--shipping-cost", type=float, help="Shipping cost")
    parser.add_argument("--stock-confirmed", type=int, help="Confirmed stock quantity")
    parser.add_argument("--direct-ship", type=_yes_no, metavar="YES_OR_NO", help="Whether the supplier direct-ships")
    parser.add_argument(
        "--verification-status", type=str.upper,
        choices=("PENDING", "VERIFIED", "REJECTED"),
        help="Manual verification status",
    )
    args = parser.parse_args(argv)
    try:
        return run(
            args.shortlist,
            args.db,
            supplier_name=args.supplier_name,
            supplier_sku=args.supplier_sku,
            supplier_cost=args.supplier_cost,
            shipping_cost=args.shipping_cost,
            stock_confirmed=args.stock_confirmed,
            direct_ship=args.direct_ship,
            verification_status=args.verification_status,
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
