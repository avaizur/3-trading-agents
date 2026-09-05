from dataclasses import dataclass
from datetime import date
from enum import Enum


class BuyingWindowStatus(str, Enum):
    UPCOMING = "UPCOMING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class RetailEvent:
    """A dated retail event and its inclusive product-buying window."""

    key: str
    name: str
    event_date: date
    buying_window_start: date
    buying_window_end: date

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("event key must not be empty")
        if not self.name.strip():
            raise ValueError("event name must not be empty")
        if self.buying_window_start > self.buying_window_end:
            raise ValueError("buying_window_start must be on or before buying_window_end")
        if self.buying_window_end > self.event_date:
            raise ValueError("buying_window_end must be on or before event_date")


@dataclass(frozen=True)
class SeasonalOpportunity:
    """A retail event evaluated for a particular day."""

    event: RetailEvent
    as_of: date
    days_until_event: int
    days_until_window_start: int
    days_until_window_end: int
    window_status: BuyingWindowStatus
    urgency_rank: int = 0

    @property
    def is_buying_window_open(self) -> bool:
        return self.window_status is BuyingWindowStatus.OPEN

