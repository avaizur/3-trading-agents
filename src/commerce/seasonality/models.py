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


@dataclass(frozen=True)
class ProductSearchProfile:
    """Editable product-search guidance for a retail event."""

    event_key: str
    categories: tuple[str, ...]
    keywords: tuple[str, ...]
    exclusions: tuple[str, ...]
    priority_score: int

    def __post_init__(self) -> None:
        if not self.event_key.strip():
            raise ValueError("event_key must not be empty")
        if not self.categories:
            raise ValueError("categories must not be empty")
        if not self.keywords:
            raise ValueError("keywords must not be empty")
        if not 1 <= self.priority_score <= 100:
            raise ValueError("priority_score must be between 1 and 100")


@dataclass(frozen=True)
class ProductSearchFocus:
    """The current seasonal event and its suggested search inputs."""

    opportunity: SeasonalOpportunity
    profile: ProductSearchProfile

    @property
    def event(self) -> RetailEvent:
        return self.opportunity.event

    @property
    def suggested_categories(self) -> tuple[str, ...]:
        return self.profile.categories

    @property
    def suggested_keywords(self) -> tuple[str, ...]:
        return self.profile.keywords
