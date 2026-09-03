from src.models.schemas import (
    CriticRecommendation, CriticReview, HealthStatus, RiskDecision,
    TraderRecommendation, VerificationResult, VerificationStatus
)

DEFAULT_MAX_RISK_PCT = 0.005
DEFAULT_MIN_REWARD_RISK = 1.5

def evaluate_trade(recommendation: TraderRecommendation,
                   verification: VerificationResult,
                   critic: CriticReview,
                   agent_health: HealthStatus,
                   account_value: float,
                   max_risk_pct: float = DEFAULT_MAX_RISK_PCT,
                   min_reward_risk: float = DEFAULT_MIN_REWARD_RISK) -> RiskDecision:
    if account_value <= 0:
        return RiskDecision(allowed=False, reason="invalid account value")
    if verification.status != VerificationStatus.VERIFIED or not verification.freshness_ok:
        return RiskDecision(allowed=False, reason="evidence not fully verified/fresh")
    if agent_health == HealthStatus.FAILED:
        return RiskDecision(allowed=False, reason="required agent FAILED")
    if critic.recommendation == CriticRecommendation.BLOCK:
        return RiskDecision(allowed=False, reason="critic blocked trade")
    if recommendation.decision.value != "BUY":
        return RiskDecision(allowed=False, reason="recommendation is not BUY")

    entry, stop, target = recommendation.entry, recommendation.stop, recommendation.target
    if None in (entry, stop, target):
        return RiskDecision(allowed=False, reason="missing trade levels")

    risk_per_unit = entry - stop
    reward_per_unit = target - entry
    if risk_per_unit <= 0:
        return RiskDecision(allowed=False, reason="invalid stop distance")

    rr = reward_per_unit / risk_per_unit
    if rr < min_reward_risk:
        return RiskDecision(allowed=False, reason="reward/risk below minimum", reward_risk=rr)

    risk_budget = account_value * max_risk_pct
    size = risk_budget / risk_per_unit

    return RiskDecision(
        allowed=True,
        reason="passed deterministic risk checks",
        position_size=size,
        planned_risk=risk_budget,
        reward_risk=rr,
    )
