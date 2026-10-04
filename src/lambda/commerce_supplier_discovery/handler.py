"""Discover conservative Go Dropship candidates for the commerce pipeline."""

from __future__ import annotations

import os

from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.godropship_discovery import (
    discover_products,
    save_new_products,
)


def lambda_handler(event, context):
    table_name = os.environ["COMMERCE_TABLE_NAME"]

    max_products = int(
        os.environ.get(
            "DISCOVERY_MAX_PRODUCTS",
            "20",
        )
    )

    store = DynamoCommerceStore(
        table_name=table_name,
    )

    products = discover_products(
        max_products=max_products,
    )

    result = save_new_products(
        store,
        products,
    )

    return {
        "ok": True,
        "supplier": "Go Dropship",
        **result,
        "products": [
            {
                "sku": item.sku,
                "title": item.title,
                "supplier_cost": item.cost,
                "stock": item.stock,
                "lane": item.lane.value,
                "source_url": item.url,
            }
            for item in products
        ],
        "publishing_performed": False,
        "ordering_performed": False,
    }
