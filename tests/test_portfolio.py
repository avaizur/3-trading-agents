from src.portfolio.exposure import evaluate_portfolio_exposure


def test_portfolio_allows_small_risk():
    result = evaluate_portfolio_exposure(
        current_open_risk_pct=0.01,
        proposed_risk_pct=0.005,
        open_positions=2,
    )

    assert result.allowed is True


def test_portfolio_blocks_excess_risk():
    result = evaluate_portfolio_exposure(
        current_open_risk_pct=0.018,
        proposed_risk_pct=0.005,
        open_positions=2,
    )

    assert result.allowed is False
