from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.commerce.ebay_inventory_service import load_access_token
from src.commerce.ebay_order_service import get_unfulfilled_orders


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value


def _safe_line_items(order: dict[str, Any]) -> list[dict[str, Any]]:
    items = []

    for line in order.get("lineItems") or []:
        if not isinstance(line, dict):
            continue

        items.append(
            {
                "sku": str(line.get("sku") or ""),
                "title": str(line.get("title") or ""),
                "quantity": int(line.get("quantity") or 0),
            }
        )

    return items


def _claim_order(table, order: dict[str, Any]) -> bool:
    order_id = str(order.get("orderId") or "")

    if not order_id:
        return False

    item = {
        "PK": f"EBAY_ORDER#{order_id}",
        "SK": "META",
        "entity_type": "EBAY_ORDER",
        "order_id": order_id,
        "creation_date": str(order.get("creationDate") or ""),
        "fulfillment_status": str(
            order.get("orderFulfillmentStatus") or ""
        ),
        "line_items": _safe_line_items(order),
        "detected_at": _now(),
        "supplier_ordering_performed": False,
    }

    try:
        table.put_item(
            Item=_to_dynamo(item),
            ConditionExpression="attribute_not_exists(PK)",
        )
        return True

    except ClientError as exc:
        code = (
            exc.response
            .get("Error", {})
            .get("Code")
        )

        if code == "ConditionalCheckFailedException":
            return False

        raise


def _format_alert(orders: list[dict[str, Any]]) -> str:
    lines = [
        "3 Trading Agents - New eBay Order",
        "",
        f"New order{'s' if len(orders) != 1 else ''}: {len(orders)}",
    ]

    for order in orders:
        lines.extend(
            [
                "",
                f"Order ID: {order.get('orderId', 'UNKNOWN')}",
                f"Created: {order.get('creationDate', '')}",
                (
                    "Fulfilment status: "
                    f"{order.get('orderFulfillmentStatus', '')}"
                ),
            ]
        )

        for item in _safe_line_items(order):
            lines.append(
                f"- {item['sku']} | {item['title']} "
                f"| quantity {item['quantity']}"
            )

    lines.extend(
        [
            "",
            "ACTION REQUIRED",
            "Place the supplier order manually and then fulfil the eBay order.",
            "",
            "AUTOMATION",
            "A safe live-listing replenishment check has been triggered.",
            "No supplier order was placed automatically.",
            "",
            "No buyer personal details are included in this alert.",
        ]
    )

    return "\n".join(lines)


def lambda_handler(event, context):
    del context
    event = event or {}

    table_name = os.environ["COMMERCE_TABLE_NAME"]
    region = os.environ.get("AWS_REGION", "eu-west-2")
    secret_id = os.environ.get(
        "EBAY_SECRET_ID",
        "3-trading-agents/ebay-production",
    )
    topic_arn = os.environ["ORDER_ALERT_TOPIC_ARN"]
    replenishment_function = os.environ[
        "REPLENISHMENT_FUNCTION_NAME"
    ]

    table = boto3.resource(
        "dynamodb",
        region_name=region,
    ).Table(table_name)

    token = load_access_token(
        secret_id=secret_id,
        region=region,
    )

    orders = get_unfulfilled_orders(token)

    new_orders = []

    for order in orders:
        if _claim_order(table, order):
            new_orders.append(order)

    if not new_orders:
        return {
            "ok": True,
            "checked": len(orders),
            "new_orders": 0,
            "alert_sent": False,
            "replenishment_invoked": False,
            "supplier_ordering_performed": False,
        }

    sns = boto3.client("sns", region_name=region)

    sns.publish(
        TopicArn=topic_arn,
        Subject=(
            "3 Trading Agents - "
            f"{len(new_orders)} new eBay order"
            f"{'s' if len(new_orders) != 1 else ''}"
        ),
        Message=_format_alert(new_orders),
    )

    lambda_client = boto3.client(
        "lambda",
        region_name=region,
    )

    lambda_client.invoke(
        FunctionName=replenishment_function,
        InvocationType="Event",
        Payload=b'{"trigger":"ebay_order"}',
    )

    return {
        "ok": True,
        "checked": len(orders),
        "new_orders": len(new_orders),
        "order_ids": [
            str(order.get("orderId"))
            for order in new_orders
        ],
        "alert_sent": True,
        "replenishment_invoked": True,
        "supplier_ordering_performed": False,
    }
