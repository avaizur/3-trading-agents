from datetime import date

import pytest

from src.commerce.product_scout import get_seasonal_focus
from src.commerce.seasonality import (
    BuyingWindowStatus,
    RetailEvent,
    SeasonalityCalendar,
    default_retail_events,
    get_top_seasonal_events,
)


def test_default_events_include_requested_examples_and_roll_into_next_year():
    events = default_retail_events(date(2026, 9, 5))

    assert [event.name for event in events] == [
        "Halloween",
        "Bonfire Night",
        "Black Friday",
        "Cyber Monday",
        "Christmas",
        "New Year",
    ]
    assert events[2].event_date == date(2026, 11, 27)
    assert events[3].event_date == date(2026, 11, 30)
    assert events[5].event_date == date(2027, 1, 1)


def test_calendar_calculates_days_and_inclusive_window_status():
    event = RetailEvent(
        key="custom",
        name="Custom Event",
        event_date=date(2026, 6, 20),
        buying_window_start=date(2026, 5, 1),
        buying_window_end=date(2026, 6, 1),
    )
    calendar = SeasonalityCalendar([event])

    result = calendar.evaluate(date(2026, 5, 1))[0]

    assert result.days_until_event == 50
    assert result.days_until_window_start == 0
    assert result.days_until_window_end == 31
    assert result.window_status is BuyingWindowStatus.OPEN
    assert result.is_buying_window_open is True


def test_events_rank_by_actionable_urgency():
    events = [
        RetailEvent("later", "Later", date(2026, 12, 1), date(2026, 10, 1), date(2026, 11, 1)),
        RetailEvent("open-later", "Open Later", date(2026, 11, 1), date(2026, 8, 1), date(2026, 10, 15)),
        RetailEvent("open-sooner", "Open Sooner", date(2026, 10, 1), date(2026, 8, 1), date(2026, 9, 15)),
    ]

    ranked = SeasonalityCalendar(events).evaluate(date(2026, 9, 1))

    assert [item.event.key for item in ranked] == ["open-sooner", "open-later", "later"]
    assert [item.urgency_rank for item in ranked] == [1, 2, 3]


def test_top_events_only_returns_windows_product_scout_can_act_on_now():
    focus = get_top_seasonal_events(date(2026, 9, 5), limit=2)

    assert [item.event.name for item in focus] == ["Halloween", "Bonfire Night"]
    assert all(item.is_buying_window_open for item in focus)
    assert get_seasonal_focus(date(2026, 9, 5), limit=2) == focus


def test_custom_events_are_supported_and_validation_is_enforced():
    custom = RetailEvent(
        key="summer-sale",
        name="Summer Sale",
        event_date=date(2027, 7, 1),
        buying_window_start=date(2027, 4, 1),
        buying_window_end=date(2027, 6, 1),
    )
    assert SeasonalityCalendar([custom]).top_events(date(2027, 5, 1))[0].event == custom

    with pytest.raises(ValueError, match="unique"):
        SeasonalityCalendar([custom, custom])
    with pytest.raises(ValueError, match="on or before event_date"):
        RetailEvent("bad", "Bad", date(2027, 1, 1), date(2026, 1, 1), date(2027, 1, 2))
    with pytest.raises(ValueError, match="non-negative"):
        SeasonalityCalendar([custom]).top_events(limit=-1)


def test_default_calendar_after_christmas_keeps_all_events_upcoming():
    as_of = date(2026, 12, 26)
    events = default_retail_events(as_of)

    assert all(event.event_date >= as_of for event in events)
    assert next(event for event in events if event.key == "christmas").event_date == date(2027, 12, 25)
