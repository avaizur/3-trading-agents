"""Daily Commerce Watch Lambda.

Reads supplier-backed products from DynamoDB, classifies their current
watch state, and persists a watch-run summary.

Safety:
- never publishes
- never reprices
- never places supplier orders
- never auto-approves
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from src.commerce.dynamo_storage import DynamoCommerceStore


TABLE_NAME = os.environ["COMMERCE_TABLE_NAME"]
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")

MARKET_EVIDENCE_MAX_AGE = timedelta(hours=24)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _watch_status(product, now: datetime) -> tuple[str, str]:
    """Return today's watch classification and reason."""

    validations_complete = all(
        (
            product.market_price_validated,
            product.platform_fees_validated,
            product.return_allowance_validated,
        )
    )

    if not validations_complete:
        return (
            "NEEDS_REFRESH",
            "Market price, platform fees, or return allowance needs validation.",
        )

    if product.updated_at is None:
        return (
            "NEEDS_REFRESH",
            "No market evidence timestamp is available.",
        )

    updated_at = product.updated_at

    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    age = now - updated_at.astimezone(timezone.utc)

    if age > MARKET_EVIDENCE_MAX_AGE:
        return (
            "NEEDS_REFRESH",
            "Market evidence is older than 24 hours.",
        )

    return (
        product.market_validation_status.value,
        "Existing market validation is still current.",
    )


def _to_dynamo(value):
    """Convert floats recursively into DynamoDB-safe Decimal values."""
    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, list):
        return [_to_dynamo(item) for item in value]

    if isinstance(value, dict):
        return {
            key: _to_dynamo(item)
            for key, item in value.items()
        }

    return value


def lambda_handler(event, context):
    now = _utc_now()
    run_id = uuid4().hex[:12]
    watch_run_id = f"WATCH#{run_id}"

    store = DynamoCommerceStore(
        table_name=TABLE_NAME,
        region_name=AWS_REGION,
    )

    products = store.list_supplier_backed_products()

    supplier_counts = Counter()
    watch_counts = Counter()
    decisions = []

    for product in products:
        supplier_counts[product.supplier_name] += 1

        watch_status, reason = _watch_status(
            product=product,
            now=now,
        )

        watch_counts[watch_status] += 1

        decisions.append(
            {
                "supplier_name": product.supplier_name,
                "supplier_sku": product.supplier_sku,
                "product_name": product.product_name,
                "market_validation_status": (
                    product.market_validation_status.value
                ),
                "watch_status": watch_status,
                "reason": reason,
                "profitable": product.profitable,
                "auto_approved": product.auto_approved,
                "published": product.published,
            }
        )

    summary = {
        "watch_run_id": watch_run_id,
        "started_at": now.isoformat(),
        "product_count": len(products),
        "supplier_counts": dict(supplier_counts),
        "watch_counts": dict(watch_counts),
        "decisions": decisions,
        "actions_taken": {
            "published": False,
            "repriced": False,
            "ordered": False,
        },
        "human_approval_required": True,
    }

    store.table.put_item(
        Item=_to_dynamo(
            {
                "PK": f"WATCH_RUN#{run_id}",
                "SK": "SUMMARY",
                "entity_type": "COMMERCE_WATCH_RUN",
                **summary,
            }
        )
    )

    return {
        "ok": True,
        "table": TABLE_NAME,
        **summary,
    }
