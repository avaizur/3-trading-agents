from datetime import datetime

from pydantic import BaseModel

from src.models.schemas import MarketSnapshot
from src.validation.data_validator import validate_market_snapshot


class MarketObservation(BaseModel):
    symbol: str
    valid: bool
    reason: str
    price: float
    volume: float | None
    source: str
    timestamp: datetime


def observe_market(snapshot: MarketSnapshot) -> MarketObservation:
    valid, reason = validate_market_snapshot(snapshot)

    return MarketObservation(
        symbol=snapshot.symbol,
        valid=valid,
        reason=reason,
        price=snapshot.price,
        volume=snapshot.volume,
        source=snapshot.source,
        timestamp=snapshot.timestamp,
    )


def run():
    return "Market Scout not connected yet"
