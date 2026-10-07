from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.adapters.registry import get_supplier_adapter
from src.commerce.ebay_inventory_service import (
    EBayInventoryError,
    get_inventory_quantity,
    get_offer,
    load_access_token,
    publish_offer,
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



def _record_result(
    *,
    store,
    live: dict,
    result: dict,
    results: list,
) -> None:
    """Append the outcome and persist it against the LIVE listing."""
    results.append(result)

    pk = live.get("PK")

    if not pk:
        sku = str(result.get("sku", ""))
        if not sku:
            return
        pk = f"LIVE_LISTING#EBAY#{sku}"

    store.table.update_item(
        Key={
            "PK": pk,
            "SK": str(live.get("SK", "META")),
        },
        UpdateExpression=(
            "SET replenishment_status = :status, "
            "replenishment_reason = :reason, "
            "replenishment_checked_at = :checked_at"
        ),
        ExpressionAttributeValues=_to_dynamo(
            {
                ":status": result.get("status", "UNKNOWN"),
                ":reason": result.get("reason", ""),
                ":checked_at": result["checked_at"],
            }
        ),
    )



def lambda_handler(event, context):
    event = event or {}
    dry_run = bool(event.get("dry_run", False))

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
            _record_result(
                store=store,
                live=live,
                result=result,
                results=results,
            )
            continue

        product = store.get_supplier_backed_product(
            "Go Dropship",
            sku,
        )

        if product is None:
            result["status"] = "BLOCKED"
            result["reason"] = "Supplier product was not found."
            _record_result(
                store=store,
                live=live,
                result=result,
                results=results,
            )
            continue

        try:
            supplier_adapter = get_supplier_adapter(
                "Go Dropship",
                store=store,
            )

            fresh_supplier = supplier_adapter.refresh_product(sku)

            if fresh_supplier is None:
                raise ValueError(
                    "Unable to refresh supplier product."
                )

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
            _record_result(
                store=store,
                live=live,
                result=result,
                results=results,
            )
            continue

        if product.supplier_stock is None or product.supplier_stock <= 0:
            result["status"] = "BLOCKED"
            result["reason"] = "Supplier stock is unavailable."
            _record_result(
                store=store,
                live=live,
                result=result,
                results=results,
            )
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
                offer = get_offer(
                    sku=sku,
                    token=ebay_token,
                )

                offer_status = str(
                    (offer or {}).get("status", "")
                ).upper()

                if offer_status != "PUBLISHED":
                    republished = publish_offer(
                        offer_id=offer_id,
                        token=ebay_token,
                    )
                    result["listing_id"] = republished["listing_id"]
                    result["republished"] = True
                    result["status"] = "IN_STOCK"
                    result["reason"] = (
                        "Inventory quantity is available and the "
                        "existing eBay offer was republished."
                    )
                else:
                    result["republished"] = False
                    result["status"] = "IN_STOCK"
                    result["reason"] = (
                        "Live eBay listing still has available quantity."
                    )

                _record_result(
                    store=store,
                    live=live,
                    result=result,
                    results=results,
                )
                continue

        except Exception as exc:
            result["status"] = "ERROR"

            if isinstance(exc, EBayInventoryError):
                safe_detail = str(exc)
            else:
                safe_detail = type(exc).__name__

            result["reason"] = (
                "Unable to read current eBay quantity: "
                f"{safe_detail}"
            )

            print(result["reason"])

            _record_result(
                store=store,
                live=live,
                result=result,
                results=results,
            )
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
            _record_result(
                store=store,
                live=live,
                result=result,
                results=results,
            )
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
            _record_result(
                store=store,
                live=live,
                result=result,
                results=results,
            )
            continue

        try:
            if ebay_token is None:
                ebay_token = load_access_token(
                    secret_id=secret_id,
                    region=region,
                )

            if dry_run:
                result["status"] = "DRY_RUN_REPLENISH"
                result["replenished"] = False
                result["target_quantity"] = 1
                result["reason"] = (
                    decision.reason
                    + " Dry run only; eBay quantity was not changed."
                )
            else:
                update_live_quantity(
                    sku=sku,
                    offer_id=offer_id,
                    quantity=1,
                    token=ebay_token,
                )

                offer = get_offer(
                    sku=sku,
                    token=ebay_token,
                )

                offer_status = (
                    str((offer or {}).get("status", "")).upper()
                )

                if offer_status != "PUBLISHED":
                    republished = publish_offer(
                        offer_id=offer_id,
                        token=ebay_token,
                    )
                    result["listing_id"] = republished["listing_id"]
                    result["republished"] = True
                else:
                    result["republished"] = False

                result["status"] = "REPLENISHED"
                result["replenished"] = True
                result["target_quantity"] = 1

        except Exception as exc:
            result["status"] = "ERROR"

            if isinstance(exc, EBayInventoryError):
                safe_detail = str(exc)
            else:
                safe_detail = type(exc).__name__

            result["reason"] = (
                "eBay quantity update failed: "
                f"{safe_detail}"
            )

            print(result["reason"])

        _record_result(
            store=store,
            live=live,
            result=result,
            results=results,
        )

    return {
        "ok": True,
        "checked": len(live_listings),
        "results": results,
        "supplier_ordering_performed": False,
        "dry_run": dry_run,
    }
