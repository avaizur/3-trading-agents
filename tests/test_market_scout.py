from datetime import datetime, timezone

from src.agents.market_scout import observe_market
from src.models.schemas import MarketSnapshot


def test_market_scout_accepts_valid_snapshot():
    snapshot = MarketSnapshot(
        symbol="TEST",
        price=100,
        volume=1000,
        timestamp=datetime.now(timezone.utc),
        source="test-source",
    )

    observation = observe_market(snapshot)

    assert observation.symbol == "TEST"
    assert observation.valid is True
    assert observation.reason == "market data valid"
    assert observation.price == 100
    assert observation.volume == 1000
    assert observation.source == "test-source"
