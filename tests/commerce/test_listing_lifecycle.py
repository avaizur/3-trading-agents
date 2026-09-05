from datetime import date, timedelta

import pytest

from src.commerce.listing_lifecycle import (
    LifecycleAction,
    ListingLifecycleSnapshot,
    ListingLifecycleStatus,
    ListingPerformance,
    ReviewStage,
    evaluate_listing_lifecycle,
    review_stage_for,
)


LISTED_ON = date(2026, 1, 1)


def snapshot(**changes):
    values = {"listing_id": "EBAY-1", "listed_on": LISTED_ON}
    values.update(changes)
    return ListingLifecycleSnapshot(**values)


def test_first_review_is_due_on_day_seven_not_before():
    item = snapshot()
    assert review_stage_for(item, LISTED_ON + timedelta(days=6)) is ReviewStage.NONE
    assert review_stage_for(item, LISTED_ON + timedelta(days=7)) is ReviewStage.FIRST


@pytest.mark.parametrize("day", [14, 17, 21, 30])
def test_second_review_is_due_from_day_fourteen_and_remains_due(day):
    item = snapshot(first_reviewed=True)
    assert review_stage_for(item, LISTED_ON + timedelta(days=day)) is ReviewStage.SECOND


def test_completed_reviews_are_not_repeated():
    item = snapshot(first_reviewed=True, second_reviewed=True)
    assert review_stage_for(item, LISTED_ON + timedelta(days=21)) is ReviewStage.NONE


@pytest.mark.parametrize(
    ("performance", "expected"),
    [
        (ListingPerformance(sales=1), ListingLifecycleStatus.WINNER),
        (ListingPerformance(views=3), ListingLifecycleStatus.PROMISING),
        (ListingPerformance(watchers=1), ListingLifecycleStatus.PROMISING),
    ],
)
def test_review_classification_is_deterministic(performance, expected):
    decision = evaluate_listing_lifecycle(
        snapshot(), performance, LISTED_ON + timedelta(days=7)
    )
    assert decision.status is expected
    assert decision.review_stage is ReviewStage.FIRST
    assert decision.human_approval_required is True
    assert decision.auto_remove is False


def test_weak_listing_can_only_be_optimised_once():
    first = evaluate_listing_lifecycle(
        snapshot(), ListingPerformance(), LISTED_ON + timedelta(days=7)
    )
    assert first.status is ListingLifecycleStatus.WEAK
    assert first.action is LifecycleAction.OPTIMISE

    already_optimised = evaluate_listing_lifecycle(
        snapshot(optimisation_count=1),
        ListingPerformance(),
        LISTED_ON + timedelta(days=7),
    )
    assert already_optimised.status is ListingLifecycleStatus.WEAK
    assert already_optimised.action is LifecycleAction.NONE

    with pytest.raises(ValueError, match="at most once"):
        snapshot(optimisation_count=2)


def test_dead_listing_is_only_marked_for_removal_at_second_review():
    decision = evaluate_listing_lifecycle(
        snapshot(first_reviewed=True, optimisation_count=1),
        ListingPerformance(),
        LISTED_ON + timedelta(days=14),
    )
    assert decision.status is ListingLifecycleStatus.DEAD
    assert decision.action is LifecycleAction.MARK_FOR_REMOVAL
    assert decision.removal_recommended is True
    assert decision.auto_remove is False
    assert decision.human_approval_required is True


def test_seasonal_listing_expires_after_not_during_event_window():
    end = LISTED_ON + timedelta(days=10)
    item = snapshot(seasonal_window_end=end)

    on_last_day = evaluate_listing_lifecycle(item, ListingPerformance(), end)
    expired = evaluate_listing_lifecycle(item, ListingPerformance(sales=10), end + timedelta(days=1))

    assert on_last_day.status is ListingLifecycleStatus.WEAK
    assert expired.status is ListingLifecycleStatus.EXPIRED_SEASON
    assert expired.action is LifecycleAction.MARK_FOR_REMOVAL
    assert expired.auto_remove is False


def test_no_review_preserves_current_status_and_recommends_no_action():
    decision = evaluate_listing_lifecycle(
        snapshot(status=ListingLifecycleStatus.PROMISING),
        ListingPerformance(),
        LISTED_ON + timedelta(days=5),
    )
    assert decision.status is ListingLifecycleStatus.PROMISING
    assert decision.action is LifecycleAction.NONE


def test_invalid_dates_and_counts_are_rejected():
    with pytest.raises(ValueError, match="before listed_on"):
        review_stage_for(snapshot(), LISTED_ON - timedelta(days=1))
    with pytest.raises(ValueError, match="non-negative"):
        ListingPerformance(views=-1)
    with pytest.raises(ValueError, match="completed first review"):
        snapshot(second_reviewed=True)
