from src.models.schemas import *
from src.risk.risk_engine import evaluate_trade

def test_valid_trade():
    rec = TraderRecommendation(
        agent="trader_a",
        symbol="TEST",
        decision="BUY",
        confidence=.7,
        entry=100,
        stop=98,
        target=104,
        holding_period="2-10 days",
    )
    ver = VerificationResult(
        symbol="TEST",
        status="VERIFIED",
        freshness_ok=True,
        verifier_confidence=.9,
    )
    crit = CriticReview(symbol="TEST", recommendation="CONTINUE")

    result = evaluate_trade(
        rec, ver, crit, HealthStatus.HEALTHY, 10000
    )

    assert result.allowed
    assert result.planned_risk == 50
    assert result.position_size == 25
