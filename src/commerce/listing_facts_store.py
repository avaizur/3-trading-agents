"""DynamoDB persistence for verified marketplace listing facts.

Listing facts are stored separately from supplier economics so serverless
publishing never depends on local JSON files.
"""

from __future__ import annotations

from typing import Any

import boto3


ENTITY_TYPE = "EBAY_LISTING_FACTS"


class ListingFactsStore:
    def __init__(
        self,
        table_name: str,
        region_name: str = "eu-west-2",
        dynamodb_resource=None,
    ):
        if dynamodb_resource is None:
            dynamodb_resource = boto3.resource(
                "dynamodb",
                region_name=region_name,
            )

        self.table = dynamodb_resource.Table(table_name)

    def save(
        self,
        *,
        sku: str,
        facts: dict[str, Any],
    ) -> dict[str, Any]:
        if not sku.strip():
            raise ValueError("SKU is required.")

        required = (
            "ebay_title",
            "ebay_category_id",
            "image_urls",
            "condition",
            "aspects",
        )

        missing = [
            key
            for key in required
            if not facts.get(key)
        ]

        if missing:
            raise ValueError(
                "Missing verified listing facts: "
                + ", ".join(missing)
            )

        item = {
            "PK": f"LISTING_FACTS#EBAY#{sku}",
            "SK": "META",
            "entity_type": ENTITY_TYPE,
            "sku": sku,
            "marketplace_id": "EBAY_GB",
            "facts": facts,
        }

        self.table.put_item(Item=item)

        return facts

    def get(self, *, sku: str) -> dict[str, Any] | None:
        response = self.table.get_item(
            Key={
                "PK": f"LISTING_FACTS#EBAY#{sku}",
                "SK": "META",
            }
        )

        item = response.get("Item")

        if not item:
            return None

        facts = item.get("facts")

        return facts if isinstance(facts, dict) else None
