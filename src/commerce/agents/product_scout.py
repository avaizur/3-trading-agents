from datetime import date

from src.commerce.seasonality import SeasonalOpportunity, get_top_seasonal_events


def run():
    return "Product Scout not connected yet"


def get_seasonal_focus(
    as_of: date | None = None,
    *,
    limit: int = 3,
) -> list[SeasonalOpportunity]:
    """Return currently open seasonal buying windows for Product Scout."""
    return get_top_seasonal_events(as_of, limit=limit, open_windows_only=True)
