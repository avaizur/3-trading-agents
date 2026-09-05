"""Deterministic, offline lifecycle recommendations for future eBay listings.

This module deliberately has no adapter or database dependencies.  Evaluating a
listing produces a recommendation; applying that recommendation remains a human
operation.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum


FIRST_REVIEW_DAY = 7
SECOND_REVIEW_START_DAY = 14
SECOND_REVIEW_END_DAY = 21


class ListingLifecycleStatus(str, Enum):
    LISTED = "LISTED"
    WINNER = "WINNER"
    PROMISING = "PROMISING"
    WEAK = "WEAK"
    DEAD = "DEAD"
    EXPIRED_SEASON = "EXPIRED_SEASON"


class ReviewStage(str, Enum):
    NONE = "NONE"
    FIRST = "FIRST"
    SECOND = "SECOND"


class LifecycleAction(str, Enum):
    NONE = "NONE"
    REVIEW = "REVIEW"
    OPTIMISE = "OPTIMISE"
    MARK_FOR_REMOVAL = "MARK_FOR_REMOVAL"


@dataclass(frozen=True)
class ListingPerformance:
    """Locally supplied cumulative performance figures for a listing."""

    sales: int = 0
    views: int = 0
    watchers: int = 0

    def __post_init__(self) -> None:
        if min(self.sales, self.views, self.watchers) < 0:
            raise ValueError("listing performance values must be non-negative")


@dataclass(frozen=True)
class ListingLifecycleSnapshot:
    listing_id: str
    listed_on: date
    status: ListingLifecycleStatus = ListingLifecycleStatus.LISTED
    first_reviewed: bool = False
    second_reviewed: bool = False
    optimisation_count: int = 0
    seasonal_window_end: date | None = None

    def __post_init__(self) -> None:
        if not self.listing_id.strip():
            raise ValueError("listing_id must not be empty")
        if self.optimisation_count < 0:
            raise ValueError("optimisation_count must be non-negative")
        if self.optimisation_count > 1:
            raise ValueError("weak listings may be optimised at most once")
        if self.second_reviewed and not self.first_reviewed:
            raise ValueError("a second review requires a completed first review")

    @property
    def optimised_once(self) -> bool:
        return self.optimisation_count == 1


@dataclass(frozen=True)
class LifecycleDecision:
    status: ListingLifecycleStatus
    review_stage: ReviewStage
    action: LifecycleAction
    reason: str
    human_approval_required: bool = True
    removal_recommended: bool = False
    auto_remove: bool = False


def review_stage_for(snapshot: ListingLifecycleSnapshot, as_of: date) -> ReviewStage:
    """Return the next due review stage; overdue reviews remain due."""
    age_days = (as_of - snapshot.listed_on).days
    if age_days < 0:
        raise ValueError("as_of cannot be before listed_on")
    if not snapshot.first_reviewed and age_days >= FIRST_REVIEW_DAY:
        return ReviewStage.FIRST
    if (
        snapshot.first_reviewed
        and not snapshot.second_reviewed
        and age_days >= SECOND_REVIEW_START_DAY
    ):
        return ReviewStage.SECOND
    return ReviewStage.NONE


def evaluate_listing_lifecycle(
    snapshot: ListingLifecycleSnapshot,
    performance: ListingPerformance,
    as_of: date,
) -> LifecycleDecision:
    """Evaluate one listing without changing it or contacting eBay.

    Any sale makes the listing a winner.  Interest without a sale makes it
    promising.  With no engagement, the first review identifies a weak listing
    and offers its single optimisation.  A still-unengaged, already-optimised
    listing becomes dead at its second review and is only marked for removal.
    """
    age_days = (as_of - snapshot.listed_on).days
    if age_days < 0:
        raise ValueError("as_of cannot be before listed_on")

    if snapshot.seasonal_window_end is not None and as_of > snapshot.seasonal_window_end:
        return LifecycleDecision(
            status=ListingLifecycleStatus.EXPIRED_SEASON,
            review_stage=ReviewStage.NONE,
            action=LifecycleAction.MARK_FOR_REMOVAL,
            reason="The seasonal event window has ended; mark the listing for human-approved removal.",
            removal_recommended=True,
        )

    stage = review_stage_for(snapshot, as_of)
    if stage is ReviewStage.NONE:
        return LifecycleDecision(
            status=snapshot.status,
            review_stage=stage,
            action=LifecycleAction.NONE,
            reason="No lifecycle review is due.",
        )

    if performance.sales > 0:
        status = ListingLifecycleStatus.WINNER
        action = LifecycleAction.REVIEW
        reason = "The listing has recorded at least one sale."
    elif performance.views > 0 or performance.watchers > 0:
        status = ListingLifecycleStatus.PROMISING
        action = LifecycleAction.REVIEW
        reason = "The listing has buyer interest but no sale yet."
    elif stage is ReviewStage.SECOND and snapshot.optimised_once:
        status = ListingLifecycleStatus.DEAD
        action = LifecycleAction.MARK_FOR_REMOVAL
        reason = "The optimised listing still has no engagement at its second review."
    else:
        status = ListingLifecycleStatus.WEAK
        action = (
            LifecycleAction.NONE
            if snapshot.optimised_once
            else LifecycleAction.OPTIMISE
        )
        reason = (
            "The listing has no engagement and has already used its one optimisation."
            if snapshot.optimised_once
            else "The listing has no engagement; one human-approved optimisation is available."
        )

    removal_recommended = action is LifecycleAction.MARK_FOR_REMOVAL
    return LifecycleDecision(
        status=status,
        review_stage=stage,
        action=action,
        reason=reason,
        removal_recommended=removal_recommended,
    )


# Concise alias for callers that already operate in the lifecycle domain.
evaluate_lifecycle = evaluate_listing_lifecycle
