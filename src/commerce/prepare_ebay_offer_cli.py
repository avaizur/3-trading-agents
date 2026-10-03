"""Prepare an eBay Inventory Item and Offer without publishing.

This command:
- creates/replaces the Inventory Item
- creates an unpublished Offer
- NEVER calls publishOffer
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

import boto3

from src.commerce.ebay_oauth import refresh_access_token
from src.commerce.prepare_listing_cli import build_description


BASE = "https://api.ebay.com/sell/inventory/v1"
DEFAULT_SECRET_ID = "3-trading-agents/ebay-production"
DEFAULT_REGION = "eu-west-2"

FULFILMENT_POLICY_ID = "333965435021"
PAYMENT_POLICY_ID = "221908907021"
RETURN_POLICY_ID = "59174312021"
MERCHANT_LOCATION_KEY = "go-dropship-uk"


def _request(
    method: str,
    path: str,
    token: str,
    payload: dict | None = None,
) -> dict:
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

    req = urllib.request.Request(
        BASE + path,
        data=body,
        method=method,
        headers=headers,
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _load_token(secret_id: str, region: str) -> str:
    secret = json.loads(
        boto3.client(
            "secretsmanager",
            region_name=region,
        )
        .get_secret_value(
            SecretId=secret_id,
        )["SecretString"]
    )

    refreshed = refresh_access_token(
        refresh_token=secret["refresh_token"],
        client_id=secret["client_id"],
        client_secret=secret["client_secret"],
    )

    token = refreshed.get("access_token")

    if not token:
        raise RuntimeError("Unable to refresh eBay access token")

    return token


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an unpublished eBay Inventory Item + Offer."
    )

    parser.add_argument("--sku", required=True)
    parser.add_argument("--price", required=True, type=float)
    parser.add_argument(
        "--facts",
        default="data/go_dropship_product_facts.json",
    )
    parser.add_argument(
        "--secret-id",
        default=DEFAULT_SECRET_ID,
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
    )

    args = parser.parse_args()

    facts_data = json.loads(Path(args.facts).read_text())

    if args.sku not in facts_data:
        raise SystemExit(
            f"BLOCKED: no verified supplier facts for {args.sku}"
        )

    facts = facts_data[args.sku]

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
        raise SystemExit(
            "BLOCKED: missing verified facts: "
            + ", ".join(missing)
        )

    token = _load_token(
        secret_id=args.secret_id,
        region=args.region,
    )

    description = build_description(facts)

    inventory_payload = {
        "availability": {
            "shipToLocationAvailability": {
                "quantity": 1,
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

    sku_path = urllib.parse.quote(args.sku, safe="")

    _request(
        "PUT",
        f"/inventory_item/{sku_path}",
        token,
        inventory_payload,
    )

    offer_payload = {
        "sku": args.sku,
        "marketplaceId": "EBAY_GB",
        "format": "FIXED_PRICE",
        "availableQuantity": 1,
        "categoryId": facts["ebay_category_id"],
        "listingDescription": description,
        "listingDuration": "GTC",
        "merchantLocationKey": MERCHANT_LOCATION_KEY,
        "pricingSummary": {
            "price": {
                "value": f"{args.price:.2f}",
                "currency": "GBP",
            }
        },
        "listingPolicies": {
            "fulfillmentPolicyId": FULFILMENT_POLICY_ID,
            "paymentPolicyId": PAYMENT_POLICY_ID,
            "returnPolicyId": RETURN_POLICY_ID,
        },
    }

    existing_query = urllib.parse.urlencode({
        "sku": args.sku,
        "marketplace_id": "EBAY_GB",
    })

    existing = _request(
        "GET",
        f"/offer?{existing_query}",
        token,
    ).get("offers", [])

    if existing:
        offer_id = existing[0]["offerId"]

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

        offer_id = created["offerId"]
        action = "CREATED"

    print("=" * 60)
    print("EBAY PREP COMPLETE")
    print("=" * 60)
    print("SKU:", args.sku)
    print("Inventory item: CREATED/UPDATED")
    print("Offer:", offer_id)
    print("Offer action:", action)
    print("Marketplace: EBAY_GB")
    print("Category:", facts["ebay_category_id"])
    print("Price:", f"£{args.price:.2f}")
    print("Images:", len(facts["image_urls"]))
    print("Published: False")
    print("Human publish approval required: True")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
