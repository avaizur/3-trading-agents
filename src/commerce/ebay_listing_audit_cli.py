from __future__ import annotations

import argparse
import json
import os
import urllib.parse
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


BASE = "https://api.ebay.com/sell/inventory/v1"


def ebay_get(path: str, token: str) -> dict:
    req = Request(
        BASE + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Language": "en-GB",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
        },
    )
    with urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show complete eBay listing readiness for one SKU."
    )
    parser.add_argument("--sku", required=True)
    parser.add_argument(
        "--facts",
        default="data/go_dropship_product_facts.json",
    )
    args = parser.parse_args()

    token = os.environ.get("EBAY_ACCESS_TOKEN")
    if not token:
        raise SystemExit("BLOCKED: EBAY_ACCESS_TOKEN is not loaded")

    sku = args.sku

    print("=" * 65)
    print("EBAY LISTING AUDIT:", sku)
    print("=" * 65)

    # ------------------------------------------------------------
    # Supplier facts
    # ------------------------------------------------------------
    facts = {}
    facts_path = Path(args.facts)

    if facts_path.exists():
        all_facts = json.loads(facts_path.read_text())
        facts = all_facts.get(sku, {})

    print("\nSUPPLIER FACTS")
    print("Title:", facts.get("ebay_title", "MISSING"))
    print("Category ID:", facts.get("ebay_category_id", "MISSING"))
    print("Condition:", facts.get("condition", "MISSING"))

    for name, values in facts.get("aspects", {}).items():
        print(f"{name}:", ", ".join(values))

    print("Images:", len(facts.get("image_urls", [])))

    # ------------------------------------------------------------
    # eBay inventory item
    # ------------------------------------------------------------
    try:
        inventory = ebay_get(
            f"/inventory_item/{urllib.parse.quote(sku, safe='')}",
            token,
        )
    except HTTPError as exc:
        print("\nINVENTORY ITEM")
        print("MISSING/ERROR HTTP:", exc.code)
        return 1

    product = inventory.get("product", {})
    availability = (
        inventory.get("availability", {})
        .get("shipToLocationAvailability", {})
    )

    print("\nEBAY INVENTORY ITEM")
    print("Condition:", inventory.get("condition"))
    print("Quantity:", availability.get("quantity"))
    print("Title:", product.get("title"))
    print("Images:", len(product.get("imageUrls", [])))

    print("\nASPECTS")
    for key, values in product.get("aspects", {}).items():
        print(f"{key}: {', '.join(values)}")

    print("\nDESCRIPTION")
    print(product.get("description", "MISSING"))

    # ------------------------------------------------------------
    # eBay offer(s) by SKU
    # ------------------------------------------------------------
    query = urllib.parse.urlencode({
        "sku": sku,
        "marketplace_id": "EBAY_GB",
    })

    offers_response = ebay_get(f"/offer?{query}", token)
    offers = offers_response.get("offers", [])

    print("\nEBAY OFFER")

    if not offers:
        print("MISSING")
        return 1

    offer = offers[0]

    price = offer.get("pricingSummary", {}).get("price", {})
    policies = offer.get("listingPolicies", {})
    listing = offer.get("listing", {})

    print("Offer ID:", offer.get("offerId"))
    print("Status:", offer.get("status"))
    print("Marketplace:", offer.get("marketplaceId"))
    print("Format:", offer.get("format"))
    print("Quantity:", offer.get("availableQuantity"))
    print("Category:", offer.get("categoryId"))
    print("Location:", offer.get("merchantLocationKey"))
    print("Price:", price.get("value"), price.get("currency"))
    print("Fulfilment policy:", policies.get("fulfillmentPolicyId"))
    print("Payment policy:", policies.get("paymentPolicyId"))
    print("Return policy:", policies.get("returnPolicyId"))
    print("Listing ID:", listing.get("listingId", "NOT PUBLISHED"))

    # ------------------------------------------------------------
    # Readiness checks
    # ------------------------------------------------------------
    checks = {
        "title": bool(product.get("title")),
        "description": bool(product.get("description")),
        "condition": bool(inventory.get("condition")),
        "quantity": availability.get("quantity") is not None,
        "aspects": bool(product.get("aspects")),
        "images": bool(product.get("imageUrls")),
        "category": bool(offer.get("categoryId")),
        "price": bool(price.get("value")),
        "fulfilment_policy": bool(policies.get("fulfillmentPolicyId")),
        "payment_policy": bool(policies.get("paymentPolicyId")),
        "return_policy": bool(policies.get("returnPolicyId")),
        "merchant_location": bool(offer.get("merchantLocationKey")),
    }

    print("\nREADINESS")
    missing = []

    for name, ok in checks.items():
        print(f"{name}: {'OK' if ok else 'MISSING'}")
        if not ok:
            missing.append(name)

    print("\n" + "=" * 65)

    if missing:
        print("SYSTEM RESULT: BLOCKED")
        print("Missing:", ", ".join(missing))
        return 2

    if offer.get("status") == "PUBLISHED":
        print("SYSTEM RESULT: ALREADY PUBLISHED")
    else:
        print("SYSTEM RESULT: READY FOR FINAL HUMAN PUBLISH REVIEW")

    print("NO PUBLISH ACTION WAS PERFORMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
