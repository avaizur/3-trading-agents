from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.adapters.registry import get_supplier_adapter
from src.commerce.ebay_inventory_service import (
    get_inventory_quantity,
    load_access_token,
    update_live_quantity,
)
from src.commerce.live_market_refresh import (
    load_ebay_adapter,
    refresh_product_market,
)
from src.commerce.replenishment import evaluate_replenishment


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dynamo(value):
    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, dict):
        return {
            key: _to_dynamo(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_to_dynamo(item) for item in value]

    return value


def lambda_handler(event, context):
    table_name = os.environ["COMMERCE_TABLE_NAME"]
    region = os.environ.get("AWS_REGION", "eu-west-2")
    secret_id = os.environ.get(
        "EBAY_SECRET_ID",
        "3-trading-agents/ebay-production",
    )

    store = DynamoCommerceStore(
        table_name=table_name,
        region_name=region,
    )

    response = store.table.scan(
        FilterExpression="entity_type = :entity_type",
        ExpressionAttributeValues={
            ":entity_type": "EBAY_LIVE_LISTING",
        },
    )

    live_listings = response.get("Items", [])

    ebay_market_adapter = None
    ebay_token = None

    results = []

    for live in live_listings:
        sku = str(live.get("sku", ""))
        offer_id = str(live.get("offer_id", ""))

        result = {
            "sku": sku,
            "listing_id": live.get("listing_id"),
            "checked_at": _now(),
            "replenished": False,
        }

        if not sku or not offer_id:
            result["status"] = "BLOCKED"
            result["reason"] = "LIVE listing is missing SKU or offer ID."
            results.append(result)
            continue

        product = store.get_supplier_backed_product(
            "Go Dropship",
            sku,
        )

        if product is None:
            result["status"] = "BLOCKED"
            result["reason"] = "Supplier product was not found."
            results.append(result)
            continue

        try:
            supplier_adapter = get_supplier_adapter("Go Dropship")

            fresh_supplier = supplier_adapter.get_product(sku)

            product.supplier_cost = fresh_supplier.cost
            product.supplier_stock = fresh_supplier.inventory_count

            if fresh_supplier.supplier_url:
                product.source_url = fresh_supplier.supplier_url

            store.save_supplier_backed_product(product)

            result["supplier_cost"] = product.supplier_cost
            result["supplier_stock"] = product.supplier_stock

        except Exception as exc:
            result["status"] = "BLOCKED"
            result["reason"] = (
                "Fresh supplier check failed: "
                f"{type(exc).__name__}"
            )
            results.append(result)
            continue

        if product.supplier_stock is None or product.supplier_stock <= 0:
            result["status"] = "BLOCKED"
            result["reason"] = "Supplier stock is unavailable."
            results.append(result)
            continue

        try:
            if ebay_token is None:
                ebay_token = load_access_token(
                    secret_id=secret_id,
                    region=region,
                )

            current_quantity = get_inventory_quantity(
                sku=sku,
                token=ebay_token,
            )

            result["current_quantity"] = current_quantity

            if current_quantity > 0:
                result["status"] = "IN_STOCK"
                result["reason"] = (
                    "Live eBay listing still has available quantity."
                )
                results.append(result)
                continue

        except Exception as exc:
            result["status"] = "ERROR"
            result["reason"] = (
                "Unable to read current eBay quantity: "
                f"{type(exc).__name__}"
            )
            results.append(result)
            continue

        try:
            if ebay_market_adapter is None:
                ebay_market_adapter = load_ebay_adapter(secret_id)

            refreshed_product, evidence = refresh_product_market(
                product=product,
                adapter=ebay_market_adapter,
            )

            if evidence.get("refreshed"):
                store.save_supplier_backed_product(
                    refreshed_product,
                )
                product = refreshed_product

        except Exception as exc:
            result["status"] = "BLOCKED"
            result["reason"] = (
                "Market refresh failed: "
                f"{type(exc).__name__}"
            )
            results.append(result)
            continue

        decision = evaluate_replenishment(
            supplier_stock=product.supplier_stock,
            expected_margin_pct=product.expected_margin,
            market_validated=(
                product.market_price_validated
                and product.platform_fees_validated
                and product.return_allowance_validated
            ),
        )

        result["expected_margin"] = product.expected_margin
        result["supplier_stock"] = product.supplier_stock
        result["reason"] = decision.reason

        if not decision.should_replenish:
            result["status"] = "BLOCKED"
            results.append(result)
            continue

        try:
            if ebay_token is None:
                ebay_token = load_access_token(
                    secret_id=secret_id,
                    region=region,
                )

            update_live_quantity(
                sku=sku,
                offer_id=offer_id,
                quantity=1,
                token=ebay_token,
            )

            result["status"] = "REPLENISHED"
            result["replenished"] = True
            result["target_quantity"] = 1

        except Exception as exc:
            result["status"] = "ERROR"
            result["reason"] = (
                "eBay quantity update failed: "
                f"{type(exc).__name__}"
            )

        results.append(result)

        store.table.update_item(
            Key={
                "PK": f"LIVE_LISTING#EBAY#{sku}",
                "SK": "META",
            },
            UpdateExpression=(
                "SET replenishment_status = :status, "
                "replenishment_reason = :reason, "
                "replenishment_checked_at = :checked_at"
            ),
            ExpressionAttributeValues=_to_dynamo(
                {
                    ":status": result["status"],
                    ":reason": result["reason"],
                    ":checked_at": result["checked_at"],
                }
            ),
        )

    return {
        "ok": True,
        "checked": len(live_listings),
        "results": results,
        "supplier_ordering_performed": False,
    }
