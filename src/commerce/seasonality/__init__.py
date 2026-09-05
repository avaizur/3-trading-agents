from .calendar import SeasonalityCalendar
from .defaults import DEFAULT_EVENT_RULES, default_retail_events
from .models import (
    BuyingWindowStatus,
    ProductSearchFocus,
    ProductSearchProfile,
    RetailEvent,
    SeasonalOpportunity,
)
from .profiles import DEFAULT_SEARCH_PROFILES, get_search_profile


def get_top_seasonal_events(
    as_of=None,
    *,
    limit: int = 3,
    open_windows_only: bool = True,
) -> list[SeasonalOpportunity]:
    calendar = SeasonalityCalendar(default_retail_events(as_of))
    return calendar.top_events(
        as_of,
        limit=limit,
        open_windows_only=open_windows_only,
    )


__all__ = [
    "BuyingWindowStatus",
    "DEFAULT_EVENT_RULES",
    "DEFAULT_SEARCH_PROFILES",
    "ProductSearchFocus",
    "ProductSearchProfile",
    "RetailEvent",
    "SeasonalOpportunity",
    "SeasonalityCalendar",
    "default_retail_events",
    "get_top_seasonal_events",
    "get_search_profile",
]
