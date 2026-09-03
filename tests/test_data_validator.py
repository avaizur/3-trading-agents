from datetime import datetime, timezone, timedelta

from src.validation.data_validator import validate_market_snapshot
from src.models.schemas import MarketSnapshot


def test_fresh_market_data_is_valid():
    snapshot = MarketSnapshot(
        symbol="TEST",
        price=100,
        volume=1000,
        timestamp=datetime.now(timezone.utc),
        source="test-source",
    )

    valid, reason = validate_market_snapshot(snapshot)

    assert valid is True


def test_stale_market_data_is_rejected():
    snapshot = MarketSnapshot(
        symbol="TEST",
        price=100,
        volume=1000,
        timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
        source="test-source",
    )

    valid, reason = validate_market_snapshot(snapshot)

    assert valid is False
