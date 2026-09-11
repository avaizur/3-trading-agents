"""Score one manually supplied eBay candidate through the higher-ticket lane."""

import argparse
from typing import Sequence

from src.commerce.higher_ticket_scoring import (
    HigherTicketEconomics,
    HigherTicketScore,
    score_higher_ticket_ebay_product,
)


# These values only translate the user-facing levels to the existing lane's
# score convention (higher score means lower risk).  The lane owns the cutoff.
RETURN_RISK_SCORES = {
    "LOW": 100,
    "MEDIUM": 50,
    "HIGH": 0,
}


def score_candidate(
    *,
    sale_price: float,
    supplier_name: str,
    supplier_basket_total: float,
    handling: float,
    delivery: float,
    platform_fees: float,
    return_allowance: float,
    return_risk_level: str,
) -> HigherTicketScore:
    """Build lane input for one candidate without persistence or API access.

    A minimal candidate has one basket amount, so that amount is both the
    supplier cost included in profit and the basket value used by supplier
    eligibility checks.
    """
    risk_level = return_risk_level.strip().upper()
    if risk_level not in RETURN_RISK_SCORES:
        raise ValueError("return-risk level must be LOW, MEDIUM, or HIGH")

    return score_higher_ticket_ebay_product(
        HigherTicketEconomics(
            sale_price=sale_price,
            supplier_cost=supplier_basket_total,
            supplier_basket_total=supplier_basket_total,
            handling_cost=handling,
            delivery_cost=delivery,
            platform_fees=platform_fees,
            return_allowance=return_allowance,
        ),
        supplier_name=supplier_name,
        return_risk_score=RETURN_RISK_SCORES[risk_level],
    )


def _print_result(result: HigherTicketScore) -> None:
    print(f"Result: {'PASS' if result.eligible_for_review else 'REJECT'}")
    print(f"Expected profit: £{result.expected_profit:.2f}")
    print(f"Margin: {result.margin_pct:.2%}")
    print("Rejection reasons:")
    if result.eligible_for_review:
        print("- None")
    else:
        for reason in result.reasons:
            print(f"- {reason}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sale-price", required=True, type=float)
    parser.add_argument("--supplier-name", required=True)
    parser.add_argument("--supplier-basket-total", required=True, type=float)
    parser.add_argument("--handling", required=True, type=float)
    parser.add_argument("--delivery", required=True, type=float)
    parser.add_argument("--platform-fees", required=True, type=float)
    parser.add_argument("--return-allowance", required=True, type=float)
    parser.add_argument(
        "--return-risk",
        required=True,
        type=str.upper,
        choices=tuple(RETURN_RISK_SCORES),
        metavar="{LOW,MEDIUM,HIGH}",
    )
    args = parser.parse_args(argv)
    try:
        result = score_candidate(
            sale_price=args.sale_price,
            supplier_name=args.supplier_name,
            supplier_basket_total=args.supplier_basket_total,
            handling=args.handling,
            delivery=args.delivery,
            platform_fees=args.platform_fees,
            return_allowance=args.return_allowance,
            return_risk_level=args.return_risk,
        )
    except ValueError as exc:
        parser.error(str(exc))
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
