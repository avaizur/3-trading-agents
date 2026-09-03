from datetime import datetime, timezone, timedelta

from src.models.schemas import MarketSnapshot


MAX_DATA_AGE_MINUTES = 30


def validate_market_snapshot(snapshot: MarketSnapshot) -> tuple[bool, str]:
    now = datetime.now(timezone.utc)

    if snapshot.timestamp.tzinfo is None:
        return False, "timestamp must be timezone-aware"

    age = now - snapshot.timestamp.astimezone(timezone.utc)

    if age < timedelta(minutes=-1):
        return False, "market data timestamp is in the future"

    if age > timedelta(minutes=MAX_DATA_AGE_MINUTES):
        return False, "market data is stale"

    if snapshot.price <= 0:
        return False, "price must be positive"

    if snapshot.volume is not None and snapshot.volume < 0:
        return False, "volume cannot be negative"

    return True, "market data valid"
