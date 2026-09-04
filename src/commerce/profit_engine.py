from typing import Optional

from src.commerce.schemas import ProfitCalculationInput, ProfitDecision

DEFAULT_MIN_MARGIN_PCT = 0.20


def calculate_profit(
    supplier_cost: float,
    shipping: float,
    platform_fee: float,
    return_buffer: float,
    sale_price: float,
    min_margin_pct: float = DEFAULT_MIN_MARGIN_PCT,
) -> ProfitDecision:
    """
    Deterministic profit and margin engine.

    Inputs:
    - supplier_cost: Unit purchase price from verified supplier
    - shipping: Inbound/outbound/fulfillment shipping costs
    - platform_fee: Platform listing & transaction fees (e.g. eBay final value fee)
    - return_buffer: Reserve for returns, claims, and damages
    - sale_price: Customer listing price
    - min_margin_pct: Target minimum profit margin ratio (default 20% / 0.20)
    """
    # Normalize min_margin_pct if supplied as percentage e.g. 20 instead of 0.20
    target_min_margin = min_margin_pct / 100.0 if min_margin_pct > 1.0 else min_margin_pct

    if supplier_cost <= 0:
        return ProfitDecision(
            allowed=False,
            reason="supplier cost must be greater than zero",
            supplier_cost=supplier_cost,
            shipping=shipping,
            platform_fee=platform_fee,
            return_buffer=return_buffer,
            total_cost=0.0,
            sale_price=sale_price,
            net_profit=0.0,
            margin_pct=0.0,
            min_margin_pct=target_min_margin,
            meets_minimum_margin=False,
        )

    if sale_price <= 0:
        return ProfitDecision(
            allowed=False,
            reason="sale price must be greater than zero",
            supplier_cost=supplier_cost,
            shipping=shipping,
            platform_fee=platform_fee,
            return_buffer=return_buffer,
            total_cost=0.0,
            sale_price=sale_price,
            net_profit=0.0,
            margin_pct=0.0,
            min_margin_pct=target_min_margin,
            meets_minimum_margin=False,
        )

    if shipping < 0 or platform_fee < 0 or return_buffer < 0:
        return ProfitDecision(
            allowed=False,
            reason="shipping, platform fee, and return buffer cannot be negative",
            supplier_cost=supplier_cost,
            shipping=shipping,
            platform_fee=platform_fee,
            return_buffer=return_buffer,
            total_cost=0.0,
            sale_price=sale_price,
            net_profit=0.0,
            margin_pct=0.0,
            min_margin_pct=target_min_margin,
            meets_minimum_margin=False,
        )

    total_cost = round(supplier_cost + shipping + platform_fee + return_buffer, 4)
    net_profit = round(sale_price - total_cost, 4)
    margin_pct = round(net_profit / sale_price, 4)

    meets_min = margin_pct >= round(target_min_margin, 4)

    if meets_min:
        reason = (
            f"Meets minimum margin requirement ({margin_pct:.2%} >= {target_min_margin:.2%})"
        )
    else:
        reason = (
            f"Margin {margin_pct:.2%} is below minimum requirement of {target_min_margin:.2%}"
        )

    return ProfitDecision(
        allowed=meets_min,
        reason=reason,
        supplier_cost=supplier_cost,
        shipping=shipping,
        platform_fee=platform_fee,
        return_buffer=return_buffer,
        total_cost=total_cost,
        sale_price=sale_price,
        net_profit=net_profit,
        margin_pct=margin_pct,
        min_margin_pct=target_min_margin,
        meets_minimum_margin=meets_min,
    )


def evaluate_profit_from_input(params: ProfitCalculationInput) -> ProfitDecision:
    """Convenience helper to evaluate profit from ProfitCalculationInput schema."""
    return calculate_profit(
        supplier_cost=params.supplier_cost,
        shipping=params.shipping,
        platform_fee=params.platform_fee,
        return_buffer=params.return_buffer,
        sale_price=params.sale_price,
        min_margin_pct=params.min_margin_pct,
    )
