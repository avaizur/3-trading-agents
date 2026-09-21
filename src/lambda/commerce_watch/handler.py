"""Daily Commerce Watch Lambda.

First production integration milestone.

This Lambda:
- uses the real DynamoCommerceStore
- loads supplier-backed products from DynamoDB
- uses the real Pydantic commerce models
- returns a small structured summary

It does NOT:
- publish to eBay
- change prices
- place supplier orders
- approve listings
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from src.commerce.dynamo_storage import DynamoCommerceStore


TABLE_NAME = os.environ["COMMERCE_TABLE_NAME"]
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")


def lambda_handler(event, context):
    run_id = f"WATCH#{uuid4().hex[:12]}"
    started_at = datetime.now(timezone.utc).isoformat()

    store = DynamoCommerceStore(
        table_name=TABLE_NAME,
        region_name=AWS_REGION,
    )

    products = store.list_supplier_backed_products()

    supplier_counts = Counter(
        product.supplier_name
        for product in products
    )

    sample_products = [
        {
            "supplier_name": product.supplier_name,
            "supplier_sku": product.supplier_sku,
        }
        for product in products[:5]
    ]

    return {
        "ok": True,
        "watch_run_id": run_id,
        "started_at": started_at,
        "table": TABLE_NAME,
        "product_count": len(products),
        "supplier_counts": dict(supplier_counts),
        "sample_products": sample_products,
        "actions_taken": {
            "published": False,
            "repriced": False,
            "ordered": False,
        },
        "human_approval_required": True,
    }
