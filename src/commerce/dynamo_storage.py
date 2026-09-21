"""DynamoDB-backed commerce storage.

Serverless production persistence for the commerce pipeline.

Current V1 support:
- SupplierBackedProduct
- SupplierPolicyRules
- ProductCandidate
- EBayListingDraft
- AgentEvaluationRecord
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Union

import boto3

from src.commerce.schemas import (
    AgentEvaluationRecord,
    CandidateStatus,
    DraftReviewStatus,
    EBayListingDraft,
    ProductCandidate,
    SupplierBackedProduct,
    SupplierPolicyRules,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


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

    @staticmethod
    def _strip_metadata(item: dict) -> dict:
        return {
            key: value
            for key, value in item.items()
            if key not in {"PK", "SK", "entity_type"}
        }

    def _scan_entity(self, entity_type: str) -> list[dict]:
        response = self.table.scan(
            FilterExpression="entity_type = :entity_type",
            ExpressionAttributeValues={
                ":entity_type": entity_type,
            },
        )
        return response.get("Items", [])

    # ------------------------------------------------------------------
    # Supplier-backed products
    # ------------------------------------------------------------------

    def save_supplier_backed_product(
        self,
        product: SupplierBackedProduct,
    ) -> SupplierBackedProduct:
        item = self._model_payload(product)
        item["PK"] = f"PRODUCT#{product.supplier_name}#{product.supplier_sku}"
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

        return SupplierBackedProduct.model_validate(
            _from_dynamo_value(self._strip_metadata(item))
        )

    def list_supplier_backed_products(self) -> list[SupplierBackedProduct]:
        products = []

        for item in self._scan_entity("SUPPLIER_BACKED_PRODUCT"):
            products.append(
                SupplierBackedProduct.model_validate(
                    _from_dynamo_value(self._strip_metadata(item))
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

        return SupplierPolicyRules.model_validate(
            _from_dynamo_value(self._strip_metadata(item))
        )

    # ------------------------------------------------------------------
    # Product candidates
    # ------------------------------------------------------------------

    def save_candidate(
        self,
        candidate: ProductCandidate,
    ) -> ProductCandidate:
        saved = candidate.model_copy(deep=True)
        now = _now()

        if saved.created_at is None:
            saved.created_at = now

        saved.updated_at = now

        item = self._model_payload(saved)
        item["PK"] = f"CANDIDATE#{saved.candidate_id}"
        item["SK"] = "META"
        item["entity_type"] = "PRODUCT_CANDIDATE"

        self.table.put_item(Item=item)
        return saved

    def get_candidate(
        self,
        candidate_id: str,
    ) -> Optional[ProductCandidate]:
        response = self.table.get_item(
            Key={
                "PK": f"CANDIDATE#{candidate_id}",
                "SK": "META",
            }
        )

        item = response.get("Item")
        if not item:
            return None

        return ProductCandidate.model_validate(
            _from_dynamo_value(self._strip_metadata(item))
        )

    def list_candidates(
        self,
        status: Optional[Union[CandidateStatus, str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProductCandidate]:
        status_value = (
            status.value
            if isinstance(status, CandidateStatus)
            else status
        )

        candidates = []

        for item in self._scan_entity("PRODUCT_CANDIDATE"):
            candidate = ProductCandidate.model_validate(
                _from_dynamo_value(self._strip_metadata(item))
            )

            if status_value is not None and candidate.status.value != status_value:
                continue

            candidates.append(candidate)

        candidates.sort(
            key=lambda item: (
                item.created_at or datetime.min.replace(tzinfo=timezone.utc),
                item.candidate_id,
            )
        )

        return candidates[offset : offset + limit]

    def get_candidates_by_sku(
        self,
        sku: str,
    ) -> list[ProductCandidate]:
        return [
            candidate
            for candidate in self.list_candidates(limit=10000)
            if candidate.sku == sku
        ]

    def update_candidate_status(
        self,
        candidate_id: str,
        new_status: Union[CandidateStatus, str],
        rejection_reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ProductCandidate:
        candidate = self.get_candidate(candidate_id)

        if candidate is None:
            raise KeyError(f"Candidate '{candidate_id}' not found.")

        candidate.status = (
            new_status
            if isinstance(new_status, CandidateStatus)
            else CandidateStatus(str(new_status))
        )

        if rejection_reason is not None:
            candidate.rejection_reason = rejection_reason

        if notes is not None:
            candidate.notes = notes

        return self.save_candidate(candidate)

    # ------------------------------------------------------------------
    # eBay listing drafts
    # ------------------------------------------------------------------

    def save_draft(
        self,
        draft: EBayListingDraft,
    ) -> EBayListingDraft:
        saved = draft.model_copy(deep=True)
        now = _now()

        if saved.draft_id is None:
            saved.draft_id = f"DRAFT-EBAY-{saved.sku}"

        if saved.created_at is None:
            saved.created_at = now

        saved.updated_at = now

        item = self._model_payload(saved)
        item["PK"] = f"DRAFT#{saved.draft_id}"
        item["SK"] = "META"
        item["entity_type"] = "EBAY_LISTING_DRAFT"

        self.table.put_item(Item=item)
        return saved

    def get_draft(
        self,
        draft_id: str,
    ) -> Optional[EBayListingDraft]:
        response = self.table.get_item(
            Key={
                "PK": f"DRAFT#{draft_id}",
                "SK": "META",
            }
        )

        item = response.get("Item")
        if not item:
            return None

        return EBayListingDraft.model_validate(
            _from_dynamo_value(self._strip_metadata(item))
        )

    def get_draft_by_candidate_id(
        self,
        candidate_id: str,
    ) -> Optional[EBayListingDraft]:
        for draft in self.list_drafts(limit=10000):
            if draft.candidate_id == candidate_id:
                return draft

        return None

    def list_drafts(
        self,
        status: Optional[Union[DraftReviewStatus, str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EBayListingDraft]:
        status_value = (
            status.value
            if isinstance(status, DraftReviewStatus)
            else status
        )

        drafts = []

        for item in self._scan_entity("EBAY_LISTING_DRAFT"):
            draft = EBayListingDraft.model_validate(
                _from_dynamo_value(self._strip_metadata(item))
            )

            if status_value is not None and draft.status.value != status_value:
                continue

            drafts.append(draft)

        drafts.sort(
            key=lambda item: (
                item.created_at or datetime.min.replace(tzinfo=timezone.utc),
                item.draft_id or "",
            )
        )

        return drafts[offset : offset + limit]

    def update_draft_status(
        self,
        draft_id: str,
        new_status: Union[DraftReviewStatus, str],
        reviewed_by: Optional[str] = None,
        rejection_reason: Optional[str] = None,
    ) -> EBayListingDraft:
        draft = self.get_draft(draft_id)

        if draft is None:
            raise KeyError(f"Draft '{draft_id}' not found.")

        new_status_value = (
            new_status
            if isinstance(new_status, DraftReviewStatus)
            else DraftReviewStatus(str(new_status))
        )

        draft.status = new_status_value

        if reviewed_by is not None:
            draft.reviewed_by = reviewed_by

        if rejection_reason is not None:
            draft.rejection_reason = rejection_reason

        if new_status_value == DraftReviewStatus.APPROVED_TO_PUBLISH:
            draft.reviewed_at = _now()

        return self.save_draft(draft)

    # ------------------------------------------------------------------
    # Agent evaluations
    # ------------------------------------------------------------------

    def save_agent_evaluation(
        self,
        evaluation: AgentEvaluationRecord,
    ) -> AgentEvaluationRecord:
        saved = evaluation.model_copy(deep=True)

        if saved.created_at is None:
            saved.created_at = _now()

        role_value = (
            saved.agent_role.value
            if hasattr(saved.agent_role, "value")
            else str(saved.agent_role)
        )

        item = self._model_payload(saved)
        item["PK"] = f"RUN#{saved.pipeline_run_id}"
        item["SK"] = f"EVAL#{role_value}"
        item["entity_type"] = "AGENT_EVALUATION"

        self.table.put_item(Item=item)
        return saved

    def list_agent_evaluations(
        self,
        supplier_sku: Optional[str] = None,
        pipeline_run_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[AgentEvaluationRecord]:
        evaluations = []

        for item in self._scan_entity("AGENT_EVALUATION"):
            evaluation = AgentEvaluationRecord.model_validate(
                _from_dynamo_value(self._strip_metadata(item))
            )

            if (
                supplier_sku is not None
                and evaluation.supplier_sku != supplier_sku
            ):
                continue

            if (
                pipeline_run_id is not None
                and evaluation.pipeline_run_id != pipeline_run_id
            ):
                continue

            evaluations.append(evaluation)

        evaluations.sort(
            key=lambda item: (
                item.created_at or datetime.min.replace(tzinfo=timezone.utc),
                item.pipeline_run_id,
                item.agent_role.value,
            )
        )

        return evaluations[:limit]
