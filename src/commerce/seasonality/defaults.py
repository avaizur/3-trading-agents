from collections.abc import Callable
from datetime import date, timedelta

from .models import RetailEvent


DateRule = Callable[[int], date]


def _fixed(month: int, day: int) -> DateRule:
    return lambda year: date(year, month, day)


def _black_friday(year: int) -> date:
    november_first = date(year, 11, 1)
    first_thursday = november_first + timedelta(days=(3 - november_first.weekday()) % 7)
    thanksgiving = first_thursday + timedelta(weeks=3)
    return thanksgiving + timedelta(days=1)


def _cyber_monday(year: int) -> date:
    return _black_friday(year) + timedelta(days=3)


# Window offsets are intentionally configuration, not business logic. They can be
# replaced by constructing a SeasonalityCalendar with the retailer's own events.
DEFAULT_EVENT_RULES: tuple[tuple[str, str, DateRule, int, int], ...] = (
    ("halloween", "Halloween", _fixed(10, 31), 120, 14),
    ("bonfire-night", "Bonfire Night", _fixed(11, 5), 90, 14),
    ("black-friday", "Black Friday", _black_friday, 120, 14),
    ("cyber-monday", "Cyber Monday", _cyber_monday, 120, 14),
    ("christmas", "Christmas", _fixed(12, 25), 120, 21),
    ("new-year", "New Year", _fixed(1, 1), 90, 14),
)


def default_retail_events(as_of: date | None = None) -> list[RetailEvent]:
    """Build the next occurrence of each example event from ``as_of``."""
    today = as_of or date.today()
    events: list[RetailEvent] = []
    for key, name, rule, start_days_before, end_days_before in DEFAULT_EVENT_RULES:
        event_date = rule(today.year)
        if event_date < today:
            event_date = rule(today.year + 1)
        events.append(
            RetailEvent(
                key=key,
                name=name,
                event_date=event_date,
                buying_window_start=event_date - timedelta(days=start_days_before),
                buying_window_end=event_date - timedelta(days=end_days_before),
            )
        )
    return events

