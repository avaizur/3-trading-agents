from src.commerce.replenishment import evaluate_replenishment


def test_replenishment_allowed_when_stock_and_margin_are_safe():
    decision = evaluate_replenishment(
        supplier_stock=12,
        expected_margin_pct=23.5,
        market_validated=True,
    )

    assert decision.should_replenish is True
    assert decision.target_quantity == 1


def test_replenishment_blocked_when_supplier_out_of_stock():
    decision = evaluate_replenishment(
        supplier_stock=0,
        expected_margin_pct=30.0,
        market_validated=True,
    )

    assert decision.should_replenish is False
    assert decision.target_quantity == 0


def test_replenishment_blocked_below_twenty_percent_margin():
    decision = evaluate_replenishment(
        supplier_stock=10,
        expected_margin_pct=19.99,
        market_validated=True,
    )

    assert decision.should_replenish is False
    assert decision.target_quantity == 0


def test_replenishment_blocked_without_current_market_validation():
    decision = evaluate_replenishment(
        supplier_stock=10,
        expected_margin_pct=25.0,
        market_validated=False,
    )

    assert decision.should_replenish is False
    assert decision.target_quantity == 0
