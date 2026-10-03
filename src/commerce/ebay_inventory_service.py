"""Reusable eBay Inventory API service for serverless commerce workflows.

This module contains no CLI behaviour and does not depend on local files.

Supported operations:
- load a short-lived eBay access token from AWS Secrets Manager
- create/update an Inventory Item
- create/update an unpublished Offer
- publish an explicitly approved Offer
- read back an Offer for verification

Publishing is deliberately a separate function so callers must invoke it
explicitly after the human-approval gate.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from typing import Any

import boto3

from src.commerce.ebay_oauth import refresh_access_token
from src.commerce.prepare_listing_cli import build_description


BASE_URL = "https://api.ebay.com/sell/inventory/v1"
DEFAULT_SECRET_ID = "3-trading-agents/ebay-production"
DEFAULT_REGION = "eu-west-2"

FULFILMENT_POLICY_ID = "333965435021"
PAYMENT_POLICY_ID = "221908907021"
RETURN_POLICY_ID = "59174312021"
MERCHANT_LOCATION_KEY = "go-dropship-uk"


class EBayInventoryError(RuntimeError):
    """Raised for eBay Inventory API failures without exposing credentials."""


def _request(
    method: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Language": "en-GB",
        "Content-Type": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
    }

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        BASE_URL + path,
        data=body,
        method=method,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")

        message = f"eBay Inventory API returned HTTP {exc.code}"

        try:
            error_payload = json.loads(raw)
            errors = error_payload.get("errors", [])

            if errors:
                safe_messages = [
                    str(item.get("message", "")).strip()
                    for item in errors
                    if item.get("message")
                ]

                if safe_messages:
                    message += ": " + " | ".join(safe_messages)

        except json.JSONDecodeError:
            pass

        raise EBayInventoryError(message) from None


def load_access_token(
    secret_id: str = DEFAULT_SECRET_ID,
    region: str = DEFAULT_REGION,
) -> str:
    """Load eBay credentials from Secrets Manager and mint an access token."""

    secret_value = (
        boto3.client(
            "secretsmanager",
            region_name=region,
        )
        .get_secret_value(
            SecretId=secret_id,
        )["SecretString"]
    )

    secret = json.loads(secret_value)

    refreshed = refresh_access_token(
        refresh_token=secret["refresh_token"],
        client_id=secret["client_id"],
        client_secret=secret["client_secret"],
    )

    token = refreshed.get("access_token")

    if not isinstance(token, str) or not token:
        raise EBayInventoryError(
            "Unable to obtain a valid eBay access token."
        )

    return token


def validate_listing_facts(facts: dict[str, Any]) -> None:
    """Validate the minimum supplier facts required for an eBay offer."""

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


def prepare_offer(
    *,
    sku: str,
    price: float,
    facts: dict[str, Any],
    token: str,
    quantity: int = 1,
) -> dict[str, Any]:
    """Create/update an Inventory Item and an unpublished eBay Offer.

    This function NEVER publishes the offer.
    """

    if not sku.strip():
        raise ValueError("SKU is required.")

    if price <= 0:
        raise ValueError("Price must be greater than zero.")

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    validate_listing_facts(facts)

    description = build_description(facts)

    inventory_payload = {
        "availability": {
            "shipToLocationAvailability": {
                "quantity": quantity,
            }
        },
        "condition": facts["condition"],
        "product": {
            "title": facts["ebay_title"],
            "description": description,
            "aspects": facts["aspects"],
            "imageUrls": facts["image_urls"],
        },
    }

    sku_path = urllib.parse.quote(sku, safe="")

    _request(
        "PUT",
        f"/inventory_item/{sku_path}",
        token,
        inventory_payload,
    )

    offer_payload = {
        "sku": sku,
        "marketplaceId": "EBAY_GB",
        "format": "FIXED_PRICE",
        "availableQuantity": quantity,
        "categoryId": str(facts["ebay_category_id"]),
        "listingDescription": description,
        "listingDuration": "GTC",
        "merchantLocationKey": MERCHANT_LOCATION_KEY,
        "pricingSummary": {
            "price": {
                "value": f"{price:.2f}",
                "currency": "GBP",
            }
        },
        "listingPolicies": {
            "fulfillmentPolicyId": FULFILMENT_POLICY_ID,
            "paymentPolicyId": PAYMENT_POLICY_ID,
            "returnPolicyId": RETURN_POLICY_ID,
        },
    }

    existing_query = urllib.parse.urlencode(
        {
            "sku": sku,
            "marketplace_id": "EBAY_GB",
        }
    )

    existing: list[dict[str, Any]] = []

    try:
        result = _request(
            "GET",
            f"/offer?{existing_query}",
            token,
        )
        existing = result.get("offers", [])

    except EBayInventoryError as exc:
        # New SKUs can legitimately have no offer yet.
        if "HTTP 404" not in str(exc):
            raise

    if existing:
        offer_id = str(existing[0]["offerId"])

        _request(
            "PUT",
            f"/offer/{offer_id}",
            token,
            offer_payload,
        )

        action = "UPDATED"

    else:
        created = _request(
            "POST",
            "/offer",
            token,
            offer_payload,
        )

        offer_id = str(created["offerId"])
        action = "CREATED"

    return {
        "sku": sku,
        "offer_id": offer_id,
        "offer_action": action,
        "marketplace_id": "EBAY_GB",
        "category_id": str(facts["ebay_category_id"]),
        "price": round(price, 2),
        "quantity": quantity,
        "image_count": len(facts["image_urls"]),
        "published": False,
        "human_publish_approval_required": True,
    }


def get_offer(
    *,
    sku: str,
    token: str,
) -> dict[str, Any] | None:
    """Return the existing EBAY_GB offer for a SKU, if present."""

    query = urllib.parse.urlencode(
        {
            "sku": sku,
            "marketplace_id": "EBAY_GB",
        }
    )

    try:
        result = _request(
            "GET",
            f"/offer?{query}",
            token,
        )

    except EBayInventoryError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise

    offers = result.get("offers", [])

    return offers[0] if offers else None


def publish_offer(
    *,
    offer_id: str,
    token: str,
) -> dict[str, Any]:
    """Publish an offer.

    Callers MUST enforce human approval before invoking this function.
    """

    if not offer_id.strip():
        raise ValueError("Offer ID is required.")

    result = _request(
        "POST",
        f"/offer/{urllib.parse.quote(offer_id, safe='')}/publish",
        token,
    )

    listing_id = result.get("listingId")

    if not listing_id:
        raise EBayInventoryError(
            "eBay publish response did not contain a listing ID."
        )

    return {
        "offer_id": offer_id,
        "listing_id": str(listing_id),
        "warnings": result.get("warnings", []),
        "published": True,
    }
