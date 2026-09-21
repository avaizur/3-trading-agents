"""Read-only live eBay market refresh for supplier-backed products."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from statistics import median

import boto3

from src.commerce.adapters.ebay_browse import EBayBrowseResearchAdapter
from src.commerce.ebay_oauth import refresh_access_token
from src.commerce.profit_engine import calculate_profit
from src.commerce.schemas import MarketValidationStatus, SupplierBackedProduct


_STOP_WORDS = {
    "and", "for", "the", "with", "from", "into", "your",
    "this", "that", "pack", "set",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) >= 3 and token not in _STOP_WORDS
    }


def _is_comparable(query: str, title: str) -> bool:
    query_tokens = _tokens(query)
    title_tokens = _tokens(title)

    if not query_tokens:
        return False

    overlap = len(query_tokens & title_tokens) / len(query_tokens)
    return overlap >= 0.5


def load_ebay_adapter(secret_id: str) -> EBayBrowseResearchAdapter:
    secret = boto3.client(
        "secretsmanager",
        region_name=os.environ.get("AWS_REGION", "eu-west-2"),
    ).get_secret_value(
        SecretId=secret_id,
    )

    payload = json.loads(secret["SecretString"])

    required = (
        "client_id",
        "client_secret",
        "refresh_token",
    )

    if any(not payload.get(key) for key in required):
        raise RuntimeError("eBay Production secret is incomplete")

    refreshed = refresh_access_token(
        refresh_token=payload["refresh_token"],
        client_id=payload["client_id"],
        client_secret=payload["client_secret"],
    )

    access_token = refreshed.get("access_token")
    if not access_token:
        raise RuntimeError("eBay access-token refresh failed")

    os.environ["EBAY_ACCESS_TOKEN"] = access_token
    os.environ["EBAY_MARKETPLACE_ID"] = payload.get(
        "marketplace_id",
        "EBAY_GB",
    )

    return EBayBrowseResearchAdapter()


def refresh_product_market(
    product: SupplierBackedProduct,
    adapter: EBayBrowseResearchAdapter,
) -> tuple[SupplierBackedProduct, dict]:
    listings = adapter.search(
        keyword=product.product_name,
        limit=20,
    )

    comparable = [
        listing
        for listing in listings
        if listing.currency == "GBP"
        and listing.price > 0
        and _is_comparable(product.product_name, listing.title)
    ]

    if not comparable:
        return product, {
            "refreshed": False,
            "reason": "No sufficiently comparable GBP eBay listings found.",
            "comparable_count": 0,
        }

    prices = [float(listing.price) for listing in comparable]
    market_price = round(float(median(prices)), 2)

    updates = {
        "market_price": market_price,
        "market_price_validated": True,
        "updated_at": datetime.now(timezone.utc),
    }

    economics_complete = (
        product.platform_fees is not None
        and product.return_allowance is not None
        and product.platform_fees_validated
        and product.return_allowance_validated
    )

    evidence = {
        "refreshed": True,
        "market_price": market_price,
        "comparable_count": len(comparable),
        "sample_item_ids": [
            listing.item_id
            for listing in comparable[:5]
        ],
    }

    if economics_complete:
        decision = calculate_profit(
            supplier_cost=product.supplier_cost,
            shipping=0.0,
            platform_fee=product.platform_fees,
            return_buffer=product.return_allowance,
            sale_price=market_price,
        )

        updates.update(
            {
                "expected_profit": decision.net_profit,
                "expected_margin": decision.margin_pct,
                "market_validation_status": (
                    MarketValidationStatus.PASS
                    if decision.allowed
                    else MarketValidationStatus.REJECT
                ),
                "profitable": decision.allowed,
                "validation_reason": decision.reason,
            }
        )

        evidence.update(
            {
                "profit_gate_run": True,
                "expected_profit": decision.net_profit,
                "expected_margin": decision.margin_pct,
                "profit_gate_allowed": decision.allowed,
            }
        )
    else:
        updates.update(
            {
                "market_validation_status": MarketValidationStatus.PENDING,
                "profitable": False,
                "validation_reason": (
                    "Live market price refreshed; fee or return inputs "
                    "still require validation."
                ),
            }
        )

        evidence["profit_gate_run"] = False

    refreshed_product = product.model_copy(
        update=updates,
    )

    return refreshed_product, evidence
