"""Create one-time human approval requests for commerce candidates."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import boto3


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def find_active_candidate_approval(
    *,
    table_name: str,
    candidate_id: str,
    region_name: str = "eu-west-2",
    dynamodb_resource=None,
) -> dict[str, Any] | None:
    """Return an existing active approval for this candidate, if one exists."""

    if dynamodb_resource is None:
        dynamodb_resource = boto3.resource(
            "dynamodb",
            region_name=region_name,
        )

    table = dynamodb_resource.Table(table_name)

    response = table.scan(
        FilterExpression=(
            "entity_type = :entity "
            "AND candidate_id = :candidate "
            "AND (#status = :pending OR #status = :publish)"
        ),
        ExpressionAttributeNames={
            "#status": "status",
        },
        ExpressionAttributeValues={
            ":entity": "COMMERCE_APPROVAL",
            ":candidate": candidate_id,
            ":pending": "PENDING",
            ":publish": "PENDING_PUBLISH",
        },
    )

    now = _utc_now()

    for item in response.get("Items", []):
        expires_raw = item.get("expires_at")

        if expires_raw:
            try:
                expires_at = datetime.fromisoformat(expires_raw)
            except ValueError:
                continue

            if expires_at <= now:
                continue

        return {
            "approval_id": item["approval_id"],
            "candidate_id": candidate_id,
            "status": item["status"],
            "expires_at": item.get("expires_at"),
            "review_url": None,
            "existing": True,
        }

    return None


def create_candidate_approval(
    *,
    table_name: str,
    candidate_id: str,
    approval_base_url: str,
    region_name: str = "eu-west-2",
    expires_hours: int = 24,
    dynamodb_resource=None,
) -> dict[str, Any]:
    if not candidate_id.strip():
        raise ValueError("candidate_id is required")

    if not approval_base_url.strip():
        raise ValueError("approval_base_url is required")

    if expires_hours <= 0:
        raise ValueError("expires_hours must be greater than zero")

    if dynamodb_resource is None:
        dynamodb_resource = boto3.resource(
            "dynamodb",
            region_name=region_name,
        )

    table = dynamodb_resource.Table(table_name)

    existing = find_active_candidate_approval(
        table_name=table_name,
        candidate_id=candidate_id,
        region_name=region_name,
        dynamodb_resource=dynamodb_resource,
    )

    if existing is not None:
        return existing

    approval_id = secrets.token_urlsafe(18)
    token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    now = _utc_now()
    expires_at = now + timedelta(hours=expires_hours)

    item = {
        "PK": f"APPROVAL#{approval_id}",
        "SK": "META",
        "entity_type": "COMMERCE_APPROVAL",
        "approval_id": approval_id,
        "candidate_id": candidate_id,
        "status": "PENDING",
        "token_hash": token_hash,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    table.put_item(
        Item=item,
        ConditionExpression=(
            "attribute_not_exists(PK)"
        ),
    )

    query = urlencode({
        "approval_id": approval_id,
        "token": token,
    })

    review_url = (
        approval_base_url.rstrip("?")
        + "?"
        + query
    )

    return {
        "approval_id": approval_id,
        "candidate_id": candidate_id,
        "status": "PENDING",
        "expires_at": expires_at.isoformat(),
        "review_url": review_url,
        "existing": False,
    }
