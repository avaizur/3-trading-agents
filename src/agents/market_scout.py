from pydantic import BaseModel

from src.models.schemas import MarketSnapshot


class MarketObservation(BaseModel):
    symbol: str
    valid: bool
    reason: str
    price: float
    volume: float | None
    source: str


def observe_market(snapshot: MarketSnapshot) -> MarketObservation:
    return MarketObservation(
        symbol=snapshot.symbol,
        valid=True,
        reason="market data valid",
        price=snapshot.price,
        volume=snapshot.volume,
        source=snapshot.source,
    )


def run():
    return "Market Scout not connected yet"
