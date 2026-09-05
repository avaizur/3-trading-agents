from datetime import date

from src.commerce.seasonality import (
    DEFAULT_SEARCH_PROFILES,
    ProductSearchFocus,
    ProductSearchProfile,
    SeasonalOpportunity,
    get_top_seasonal_events,
)


def run():
    return "Product Scout not connected yet"


def get_seasonal_focus(
    as_of: date | None = None,
    *,
    limit: int = 3,
) -> list[SeasonalOpportunity]:
    """Return currently open seasonal buying windows for Product Scout."""
    return get_top_seasonal_events(as_of, limit=limit, open_windows_only=True)


def get_current_search_focus(
    as_of: date | None = None,
    *,
    profiles: dict[str, ProductSearchProfile] | None = None,
) -> ProductSearchFocus | None:
    """Return the top actionable event with its product-search suggestions."""
    profile_config = DEFAULT_SEARCH_PROFILES if profiles is None else profiles
    top_events = get_seasonal_focus(as_of, limit=1)
    if not top_events:
        return None

    opportunity = top_events[0]
    profile = profile_config.get(opportunity.event.key)
    if profile is None:
        return None
    return ProductSearchFocus(opportunity=opportunity, profile=profile)
