from dataclasses import dataclass


MIN_MARGIN_PCT = 20.0


@dataclass(frozen=True)
class ReplenishmentDecision:
    should_replenish: bool
    target_quantity: int
    reason: str


def evaluate_replenishment(
    *,
    supplier_stock: int | None,
    expected_margin_pct: float | None,
    market_validated: bool,
    min_margin_pct: float = MIN_MARGIN_PCT,
) -> ReplenishmentDecision:
    """
    Decide whether a sold marketplace listing may be replenished to quantity 1.

    This function never places supplier orders and never contacts a marketplace.
    """

    if supplier_stock is None or supplier_stock <= 0:
        return ReplenishmentDecision(
            should_replenish=False,
            target_quantity=0,
            reason="Supplier stock is unavailable.",
        )

    if not market_validated:
        return ReplenishmentDecision(
            should_replenish=False,
            target_quantity=0,
            reason="Current marketplace economics have not been validated.",
        )

    if expected_margin_pct is None:
        return ReplenishmentDecision(
            should_replenish=False,
            target_quantity=0,
            reason="Current expected margin is unavailable.",
        )

    if expected_margin_pct < min_margin_pct:
        return ReplenishmentDecision(
            should_replenish=False,
            target_quantity=0,
            reason=(
                f"Expected margin {expected_margin_pct:.2f}% "
                f"is below the {min_margin_pct:.2f}% minimum."
            ),
        )

    return ReplenishmentDecision(
        should_replenish=True,
        target_quantity=1,
        reason=(
            "Supplier stock is available and current marketplace "
            f"margin is {expected_margin_pct:.2f}%."
        ),
    )
