"""Build verified eBay listing facts for supplier products."""

from __future__ import annotations

import os

from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.ebay_listing_facts_builder import (
    build_verified_listing_facts,
)
from src.commerce.godropship_discovery import _fetch
from src.commerce.listing_facts_store import ListingFactsStore


def lambda_handler(event, context):
    table_name = os.environ["COMMERCE_TABLE_NAME"]

    supplier_name = event["supplier_name"]
    supplier_sku = event["supplier_sku"]
    source_url = event["source_url"]

    store = DynamoCommerceStore(
        table_name=table_name,
    )

    product = store.get_supplier_backed_product(
        supplier_name,
        supplier_sku,
    )

    if product is None:
        return {
            "ok": False,
            "status": "PRODUCT_NOT_FOUND",
            "supplier_sku": supplier_sku,
        }

    supplier_html = _fetch(source_url)

    facts = build_verified_listing_facts(
        title=product.product_name,
        supplier_html=supplier_html,
    )

    if not facts["image_urls"]:
        return {
            "ok": False,
            "status": "NEEDS_LISTING_FACTS",
            "supplier_sku": supplier_sku,
            "reason": "No supplier images found.",
            "missing_required_aspects": (
                facts["missing_required_aspects"]
            ),
        }

    if not facts["listing_facts_complete"]:
        return {
            "ok": False,
            "status": "NEEDS_LISTING_FACTS",
            "supplier_sku": supplier_sku,
            "category_id": facts["ebay_category_id"],
            "category_name": facts["ebay_category_name"],
            "missing_required_aspects": (
                facts["missing_required_aspects"]
            ),
            "image_count": len(facts["image_urls"]),
        }

    save_payload = {
        "ebay_title": facts["ebay_title"],
        "ebay_category_id": facts["ebay_category_id"],
        "image_urls": facts["image_urls"],
        "condition": facts["condition"],
        "aspects": facts["aspects"],
    }

    ListingFactsStore(
        table_name=table_name,
    ).save(
        sku=supplier_sku,
        facts=save_payload,
    )

    return {
        "ok": True,
        "status": "LISTING_FACTS_READY",
        "supplier_sku": supplier_sku,
        "category_id": facts["ebay_category_id"],
        "category_name": facts["ebay_category_name"],
        "image_count": len(facts["image_urls"]),
        "aspects": facts["aspects"],
    }
