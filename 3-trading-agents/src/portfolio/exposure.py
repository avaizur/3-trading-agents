from src.models.schemas import PortfolioDecision

def evaluate_portfolio_exposure(current_open_risk_pct: float,
                                proposed_risk_pct: float,
                                open_positions: int,
                                max_total_open_risk_pct: float = 0.02,
                                max_open_positions: int = 5) -> PortfolioDecision:
    if open_positions >= max_open_positions:
        return PortfolioDecision(
            allowed=False,
            reason="maximum open positions reached",
            total_open_risk_pct=current_open_risk_pct,
        )

    new_total = current_open_risk_pct + proposed_risk_pct

    if new_total > max_total_open_risk_pct:
        return PortfolioDecision(
            allowed=False,
            reason="maximum total risk exceeded",
            total_open_risk_pct=new_total,
        )

    return PortfolioDecision(
        allowed=True,
        reason="portfolio exposure acceptable",
        total_open_risk_pct=new_total,
    )
