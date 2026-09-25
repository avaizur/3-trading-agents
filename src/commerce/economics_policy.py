"""Deterministic commerce economics policy for the current eBay UK setup."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MIN_MARGIN_PCT = 0.20
DEFAULT_RETURN_BUFFER_RATE = 0.05


@dataclass(frozen=True)
class EconomicsInputs:
    platform_fee: float
    return_allowance: float
    shipping: float


def ebay_uk_private_economics(
    sale_price: float,
    *,
    supplier_name: str,
) -> EconomicsInputs:
    """Return deterministic economics inputs for the current UK private-seller setup."""

    if sale_price <= 0:
        raise ValueError("sale_price must be positive")

    platform_fee = 0.0
    return_allowance = round(sale_price * DEFAULT_RETURN_BUFFER_RATE, 2)

    shipping = 0.0 if supplier_name == "Go Dropship" else 0.0

    return EconomicsInputs(
        platform_fee=platform_fee,
        return_allowance=return_allowance,
        shipping=shipping,
    )
