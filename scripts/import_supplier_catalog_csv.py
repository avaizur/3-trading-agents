"""Import supplier catalogue products into DynamoDB as PENDING products.

This command does not perform market validation, profitability decisions,
agent approval, listing creation, publishing, repricing, or ordering.
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.schemas import ProductLane, SupplierBackedProduct


def _required(row: dict[str, str], column: str) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        raise ValueError(f"Missing required value in column: {column}")
    return value


def import_catalog(
    path: str,
    *,
    table_name: str,
    supplier_name: str,
    lane: ProductLane,
    sku_column: str,
    title_column: str,
    cost_column: str,
) -> tuple[int, int]:
    store = DynamoCommerceStore(table_name=table_name)

    imported = 0
    skipped = 0

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)

        if not reader.fieldnames:
            raise ValueError("Catalogue CSV has no header row.")

        required_columns = {sku_column, title_column, cost_column}
        missing = required_columns - set(reader.fieldnames)
        if missing:
            raise ValueError(
                "Catalogue CSV is missing required columns: "
                + ", ".join(sorted(missing))
            )

        for line_number, row in enumerate(reader, start=2):
            sku = _required(row, sku_column)
            title = _required(row, title_column)

            try:
                cost = float(_required(row, cost_column))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid supplier cost on CSV line {line_number}"
                ) from exc

            if cost <= 0:
                raise ValueError(
                    f"Supplier cost must be greater than zero on line {line_number}"
                )

            existing = store.get_supplier_backed_product(
                supplier_name,
                sku,
            )

            if existing is not None:
                skipped += 1
                continue

            product = SupplierBackedProduct(
                supplier_name=supplier_name,
                supplier_sku=sku,
                product_name=title,
                supplier_cost=cost,
                lane=lane,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            store.save_supplier_backed_product(product)
            imported += 1

    return imported, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("catalogue", help="Supplier catalogue CSV file")
    parser.add_argument(
        "--table-name",
        default=os.environ.get(
            "COMMERCE_TABLE_NAME",
            "3-trading-agents-commerce-v1",
        ),
    )
    parser.add_argument("--supplier-name", required=True)
    parser.add_argument(
        "--lane",
        required=True,
        choices=[lane.value for lane in ProductLane],
    )

    parser.add_argument("--sku-column", required=True)
    parser.add_argument("--title-column", required=True)
    parser.add_argument("--cost-column", required=True)

    args = parser.parse_args()

    imported, skipped = import_catalog(
        args.catalogue,
        table_name=args.table_name,
        supplier_name=args.supplier_name,
        lane=ProductLane(args.lane),
        sku_column=args.sku_column,
        title_column=args.title_column,
        cost_column=args.cost_column,
    )

    print(f"Imported: {imported}")
    print(f"Already present: {skipped}")
    print("All imported products remain PENDING market validation.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
