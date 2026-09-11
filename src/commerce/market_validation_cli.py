"""Batch-validate staged supplier products using confirmed marketplace economics."""

import argparse
import json
from pathlib import Path
from typing import Sequence

from pydantic import TypeAdapter, ValidationError

from src.commerce.database import CommerceDatabase
from src.commerce.profit_engine import calculate_profit
from src.commerce.schemas import (
    MarketValidationStatus,
    SupplierMarketValidationInput,
    SupplierMarketValidationResult,
)


def load_validation_inputs(path: str) -> list[SupplierMarketValidationInput]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("validations") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise ValueError("Market validation batch must be a non-empty JSON array.")
    try:
        return TypeAdapter(list[SupplierMarketValidationInput]).validate_python(rows)
    except ValidationError as exc:
        raise ValueError(f"Invalid market validation input: {exc}") from exc


def validate_market_batch(
    db_path: str, inputs: list[SupplierMarketValidationInput]
) -> list[SupplierMarketValidationResult]:
    if not inputs:
        raise ValueError("Market validation batch is empty.")
    db = CommerceDatabase(db_path)
    results = []
    seen = set()
    for item in inputs:
        key = (item.supplier_name, item.supplier_sku)
        if key in seen:
            raise ValueError("Market validation batch contains duplicate products.")
        seen.add(key)
        product = db.get_supplier_backed_product(*key)
        if product is None:
            raise KeyError(f"Staged product '{item.supplier_name}/{item.supplier_sku}' not found.")
        decision = calculate_profit(
            supplier_cost=product.supplier_cost,
            shipping=0.0,
            platform_fee=item.platform_fee_estimate,
            return_buffer=item.return_allowance,
            sale_price=item.marketplace_sale_price,
        )
        results.append(SupplierMarketValidationResult(
            supplier_name=item.supplier_name,
            supplier_sku=item.supplier_sku,
            marketplace_sale_price=item.marketplace_sale_price,
            platform_fee_estimate=item.platform_fee_estimate,
            return_allowance=item.return_allowance,
            expected_profit=decision.net_profit,
            expected_margin=decision.margin_pct,
            status=(MarketValidationStatus.PASS if decision.allowed
                    else MarketValidationStatus.REJECT),
            reason=decision.reason,
        ))
    return db.save_supplier_market_validations(results)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON file containing validated market inputs")
    parser.add_argument("--db", default="data/commerce.db", help="SQLite database path")
    args = parser.parse_args(argv)
    try:
        results = validate_market_batch(args.db, load_validation_inputs(args.input))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    for result in results:
        print(
            f"{result.supplier_sku}: {result.status.value} | "
            f"profit £{result.expected_profit:.2f} | margin {result.expected_margin:.2%}"
        )
    print("No products were approved or published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
