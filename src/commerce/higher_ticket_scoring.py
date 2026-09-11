"""Conservative, offline scoring for higher-ticket eBay opportunities.

This lane only recommends products for human review.  It deliberately has no
integration with listing approval or publishing.
"""

from dataclasses import dataclass
from enum import Enum


MIN_SALE_PRICE = 35.0
MAX_SALE_PRICE = 80.0
MIN_EXPECTED_PROFIT = 7.0
MIN_MARGIN_PCT = 0.20
WICKED_NIGHTS_MINIMUM_BASKET = 25.0
MIN_ACCEPTABLE_RETURN_RISK_SCORE = 50


class HigherTicketDecision(str, Enum):
    """Outcomes are recommendations, not listing lifecycle statuses."""

    REVIEW = "REVIEW"
    REJECT = "REJECT"


@dataclass(frozen=True)
class HigherTicketEconomics:
    sale_price: float
    supplier_cost: float
    supplier_basket_total: float
    supplier_basket_minimum: float = 0.0
    handling_cost: float = 0.0
    delivery_cost: float = 0.0
    platform_fees: float = 0.0
    return_allowance: float = 0.0


@dataclass(frozen=True)
class HigherTicketScore:
    decision: HigherTicketDecision
    expected_profit: float
    margin_pct: float
    total_cost: float
    reasons: tuple[str, ...]
    human_review_required: bool = True
    auto_approved: bool = False
    publish_allowed: bool = False

    @property
    def eligible_for_review(self) -> bool:
        return self.decision is HigherTicketDecision.REVIEW


def score_higher_ticket_ebay_product(
    economics: HigherTicketEconomics,
    *,
    supplier_name: str,
    return_risk_score: int,
) -> HigherTicketScore:
    """Apply every higher-ticket gate and return a non-actioning recommendation.

    ``return_risk_score`` follows :mod:`opportunity_scoring`: a higher value
    means a lower likelihood of return.  Scores below 50 are treated as high
    risk; low and medium risk products remain eligible.
    """
    amounts = {
        "sale price": economics.sale_price,
        "supplier cost": economics.supplier_cost,
        "supplier basket total": economics.supplier_basket_total,
        "supplier basket minimum": economics.supplier_basket_minimum,
        "handling": economics.handling_cost,
        "delivery": economics.delivery_cost,
        "platform fees": economics.platform_fees,
        "return allowance": economics.return_allowance,
    }
    if any(value < 0 for value in amounts.values()):
        invalid = ", ".join(name for name, value in amounts.items() if value < 0)
        raise ValueError(f"Costs and thresholds cannot be negative: {invalid}.")
    if not 0 <= return_risk_score <= 100:
        raise ValueError("return_risk_score must be between 0 and 100.")

    total_cost = round(
        economics.supplier_cost
        + economics.handling_cost
        + economics.delivery_cost
        + economics.platform_fees
        + economics.return_allowance,
        4,
    )
    expected_profit = round(economics.sale_price - total_cost, 4)
    margin_pct = (
        round(expected_profit / economics.sale_price, 4)
        if economics.sale_price > 0
        else 0.0
    )

    reasons: list[str] = []
    if not MIN_SALE_PRICE <= economics.sale_price <= MAX_SALE_PRICE:
        reasons.append(
            f"Sale price must be between £{MIN_SALE_PRICE:.0f} and £{MAX_SALE_PRICE:.0f}."
        )
    if economics.supplier_basket_total < economics.supplier_basket_minimum:
        reasons.append(
            "Supplier basket total does not meet the supplier basket minimum."
        )
    if (
        _is_wicked_nights(supplier_name)
        and economics.supplier_basket_total < WICKED_NIGHTS_MINIMUM_BASKET
    ):
        reasons.append("Wicked Nights requires a supplier basket of at least £25.")
    if expected_profit < MIN_EXPECTED_PROFIT:
        reasons.append(f"Expected profit must be at least £{MIN_EXPECTED_PROFIT:.0f}.")
    if margin_pct < MIN_MARGIN_PCT:
        reasons.append(f"Expected margin must be at least {MIN_MARGIN_PCT:.0%}.")
    if return_risk_score < MIN_ACCEPTABLE_RETURN_RISK_SCORE:
        reasons.append("High return-risk products are not eligible for this lane.")

    return HigherTicketScore(
        decision=(
            HigherTicketDecision.REJECT if reasons else HigherTicketDecision.REVIEW
        ),
        expected_profit=expected_profit,
        margin_pct=margin_pct,
        total_cost=total_cost,
        reasons=tuple(reasons) or (
            "Meets the higher-ticket gates; send for human review only.",
        ),
    )


def _is_wicked_nights(supplier_name: str) -> bool:
    return "".join(character for character in supplier_name.casefold() if character.isalnum()) == "wickednights"
