"""DynamoDB-backed commerce storage.

V1 supports:
- SupplierBackedProduct
- SupplierPolicyRules

Additional commerce entities will be added incrementally.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

from src.commerce.schemas import SupplierBackedProduct, SupplierPolicyRules


def _to_dynamo_value(value: Any) -> Any:
    """Convert Python/Pydantic values into DynamoDB-safe values."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_dynamo_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_dynamo_value(v) for k, v in value.items()}
    return value


def _from_dynamo_value(value: Any) -> Any:
    """Convert DynamoDB Decimal values back into normal Python values."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_from_dynamo_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_dynamo_value(v) for k, v in value.items()}
    return value


class DynamoCommerceStore:
    """DynamoDB implementation of the commerce storage contract."""

    def __init__(
        self,
        table_name: str,
        region_name: str = "eu-west-2",
        dynamodb_resource=None,
    ):
        self.table_name = table_name

        if dynamodb_resource is None:
            dynamodb_resource = boto3.resource(
                "dynamodb",
                region_name=region_name,
            )

        self.table = dynamodb_resource.Table(table_name)

    @staticmethod
    def _model_payload(model) -> dict:
        payload = model.model_dump(mode="json")
        return _to_dynamo_value(payload)

    # ------------------------------------------------------------------
    # Supplier-backed products
    # ------------------------------------------------------------------

    def save_supplier_backed_product(
        self,
        product: SupplierBackedProduct,
    ) -> SupplierBackedProduct:
        item = self._model_payload(product)

        item["PK"] = (
            f"PRODUCT#{product.supplier_name}#{product.supplier_sku}"
        )
        item["SK"] = "META"
        item["entity_type"] = "SUPPLIER_BACKED_PRODUCT"

        self.table.put_item(Item=item)
        return product

    def get_supplier_backed_product(
        self,
        supplier_name: str,
        supplier_sku: str,
    ) -> Optional[SupplierBackedProduct]:
        response = self.table.get_item(
            Key={
                "PK": f"PRODUCT#{supplier_name}#{supplier_sku}",
                "SK": "META",
            }
        )

        item = response.get("Item")
        if not item:
            return None

        payload = {
            key: value
            for key, value in item.items()
            if key not in {"PK", "SK", "entity_type"}
        }

        return SupplierBackedProduct.model_validate(
            _from_dynamo_value(payload)
        )

    def list_supplier_backed_products(self) -> list[SupplierBackedProduct]:
        response = self.table.scan(
            FilterExpression="entity_type = :entity_type",
            ExpressionAttributeValues={
                ":entity_type": "SUPPLIER_BACKED_PRODUCT",
            },
        )

        products: list[SupplierBackedProduct] = []

        for item in response.get("Items", []):
            payload = {
                key: value
                for key, value in item.items()
                if key not in {"PK", "SK", "entity_type"}
            }

            products.append(
                SupplierBackedProduct.model_validate(
                    _from_dynamo_value(payload)
                )
            )

        return products

    # ------------------------------------------------------------------
    # Supplier policies
    # ------------------------------------------------------------------

    def save_supplier_policy_rules(
        self,
        rules: SupplierPolicyRules,
    ) -> SupplierPolicyRules:
        item = self._model_payload(rules)

        item["PK"] = f"SUPPLIER#{rules.supplier_id}"
        item["SK"] = "POLICY"
        item["entity_type"] = "SUPPLIER_POLICY"

        self.table.put_item(Item=item)
        return rules

    def get_supplier_policy_rules(
        self,
        supplier_id: str,
    ) -> Optional[SupplierPolicyRules]:
        response = self.table.get_item(
            Key={
                "PK": f"SUPPLIER#{supplier_id}",
                "SK": "POLICY",
            }
        )

        item = response.get("Item")
        if not item:
            return None

        payload = {
            key: value
            for key, value in item.items()
            if key not in {"PK", "SK", "entity_type"}
        }

        return SupplierPolicyRules.model_validate(
            _from_dynamo_value(payload)
        )
