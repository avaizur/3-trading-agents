#!/usr/bin/env python3

"""Migrate supplier-backed products from local SQLite to DynamoDB.

Safe defaults:
- dry-run unless --write is supplied
- validates every row through SupplierBackedProduct
- preserves PASS / REJECT / PENDING state
- preserves human-safety guardrails
- never publishes or auto-approves anything
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.schemas import SupplierBackedProduct


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "commerce.db"
DEFAULT_TABLE = "3-trading-agents-commerce-v1"


def sqlite_row_to_product(row: sqlite3.Row) -> SupplierBackedProduct:
    return SupplierBackedProduct(
        id=row["id"],
        supplier_name=row["supplier_name"],
        supplier_sku=row["supplier_sku"],
        product_name=row["product_name"],
        supplier_cost=row["supplier_cost"],
        lane=row["lane"],
        market_price=row["market_price"],
        platform_fees=row["platform_fees"],
        return_allowance=row["return_allowance"],
        market_price_validated=bool(row["market_price_validated"]),
        platform_fees_validated=bool(row["platform_fees_validated"]),
        return_allowance_validated=bool(row["return_allowance_validated"]),
        expected_profit=row["expected_profit"],
        expected_margin=row["expected_margin"],
        market_validation_status=row["market_validation_status"],
        validation_reason=row["validation_reason"],
        profitable=bool(row["profitable"]),
        auto_approved=bool(row["auto_approved"]),
        published=bool(row["published"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row

    rows = db.execute(
        """
        SELECT *
        FROM supplier_backed_products
        ORDER BY supplier_name, supplier_sku
        LIMIT ?
        """,
        (args.limit,),
    ).fetchall()

    products: list[SupplierBackedProduct] = []

    for row in rows:
        product = sqlite_row_to_product(row)
        products.append(product)

        print(
            f"VALID | {product.supplier_name} | "
            f"{product.supplier_sku} | "
            f"{product.market_validation_status.value} | "
            f"profitable={product.profitable} | "
            f"auto_approved={product.auto_approved} | "
            f"published={product.published}"
        )

    print(f"\nvalidated={len(products)}")

    if not args.write:
        print("mode=DRY_RUN")
        print("No DynamoDB writes performed.")
        return

    store = DynamoCommerceStore(table_name=args.table)

    for product in products:
        store.save_supplier_backed_product(product)
        print(
            f"WROTE | {product.supplier_name} | "
            f"{product.supplier_sku}"
        )

    print(f"\nwritten={len(products)}")
    print(f"table={args.table}")


if __name__ == "__main__":
    main()
