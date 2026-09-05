from collections.abc import Iterable
from datetime import date

from .models import BuyingWindowStatus, RetailEvent, SeasonalOpportunity


class SeasonalityCalendar:
    """Evaluates and ranks a configurable collection of dated retail events."""

    def __init__(self, events: Iterable[RetailEvent]):
        self.events = tuple(events)
        keys = [event.key for event in self.events]
        if len(keys) != len(set(keys)):
            raise ValueError("event keys must be unique")

    def evaluate(
        self,
        as_of: date | None = None,
        *,
        include_past_events: bool = False,
    ) -> list[SeasonalOpportunity]:
        today = as_of or date.today()
        opportunities = [
            self._evaluate_event(event, today)
            for event in self.events
            if include_past_events or event.event_date >= today
        ]
        opportunities.sort(key=self._urgency_key)
        return [
            SeasonalOpportunity(
                event=item.event,
                as_of=item.as_of,
                days_until_event=item.days_until_event,
                days_until_window_start=item.days_until_window_start,
                days_until_window_end=item.days_until_window_end,
                window_status=item.window_status,
                urgency_rank=rank,
            )
            for rank, item in enumerate(opportunities, start=1)
        ]

    def top_events(
        self,
        as_of: date | None = None,
        *,
        limit: int = 3,
        open_windows_only: bool = True,
    ) -> list[SeasonalOpportunity]:
        """Return the highest-urgency events for Product Scout attention."""
        if limit < 0:
            raise ValueError("limit must be non-negative")
        ranked = self.evaluate(as_of)
        if open_windows_only:
            ranked = [item for item in ranked if item.is_buying_window_open]
        return ranked[:limit]

    @staticmethod
    def _evaluate_event(event: RetailEvent, as_of: date) -> SeasonalOpportunity:
        if as_of < event.buying_window_start:
            status = BuyingWindowStatus.UPCOMING
        elif as_of <= event.buying_window_end:
            status = BuyingWindowStatus.OPEN
        else:
            status = BuyingWindowStatus.CLOSED
        return SeasonalOpportunity(
            event=event,
            as_of=as_of,
            days_until_event=(event.event_date - as_of).days,
            days_until_window_start=(event.buying_window_start - as_of).days,
            days_until_window_end=(event.buying_window_end - as_of).days,
            window_status=status,
        )

    @staticmethod
    def _urgency_key(item: SeasonalOpportunity) -> tuple[int, int, int, str]:
        # Open windows rank first, with the soonest-closing window most urgent.
        # Upcoming windows follow by opening date; already-closed windows are last.
        if item.window_status is BuyingWindowStatus.OPEN:
            return (0, item.days_until_window_end, item.days_until_event, item.event.key)
        if item.window_status is BuyingWindowStatus.UPCOMING:
            return (1, item.days_until_window_start, item.days_until_event, item.event.key)
        return (2, item.days_until_event, 0, item.event.key)

