"""Serverless supplier catalogue ingestion from S3 CSV."""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3

from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.schemas import ProductLane, SupplierBackedProduct


s3 = boto3.client("s3")


def _required(row: dict[str, str], column: str) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        raise ValueError(f"Missing required value in column: {column}")
    return value


def _process_csv(body: str) -> dict:
    table_name = os.environ["COMMERCE_TABLE_NAME"]
    supplier_name = os.environ["SUPPLIER_NAME"]
    lane = ProductLane(os.environ.get("PRODUCT_LANE", "EVERGREEN"))

    sku_column = os.environ.get("SKU_COLUMN", "sku")
    title_column = os.environ.get("TITLE_COLUMN", "title")
    cost_column = os.environ.get("COST_COLUMN", "cost")

    store = DynamoCommerceStore(table_name=table_name)

    reader = csv.DictReader(io.StringIO(body))

    if not reader.fieldnames:
        raise ValueError("Catalogue CSV has no header row.")

    required_columns = {sku_column, title_column, cost_column}
    missing = required_columns - set(reader.fieldnames)

    if missing:
        raise ValueError(
            "Catalogue CSV missing required columns: "
            + ", ".join(sorted(missing))
        )

    imported = 0
    skipped = 0

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

        now = datetime.now(timezone.utc)

        product = SupplierBackedProduct(
            supplier_name=supplier_name,
            supplier_sku=sku,
            product_name=title,
            supplier_cost=cost,
            lane=lane,
            created_at=now,
            updated_at=now,
        )

        store.save_supplier_backed_product(product)
        imported += 1

    return {
        "imported": imported,
        "skipped": skipped,
    }


def lambda_handler(event, context):
    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        response = s3.get_object(
            Bucket=bucket,
            Key=key,
        )

        body = response["Body"].read().decode("utf-8-sig")

        result = _process_csv(body)

        results.append(
            {
                "bucket": bucket,
                "key": key,
                **result,
            }
        )

    return {
        "ok": True,
        "files_processed": len(results),
        "results": results,
    }
