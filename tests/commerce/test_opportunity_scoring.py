from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.commerce.market_research import MarketListing
from src.commerce.opportunity_scoring import (
    MarketOpportunityScorer,
    OpportunityDecision,
    ScoredMarketOpportunity,
    shortlist_candidates,
)
from src.commerce.product_scout import get_current_search_focus


def listing(
    item_id,
    title,
    price,
    *,
    category="Party Decorations",
    seller="trusted_seller",
    condition="New",
    availability="IN_STOCK",
    end_date=datetime(2026, 10, 20, tzinfo=timezone.utc),
):
    return MarketListing(
        title=title,
        item_id=item_id,
        price=Decimal(price),
        currency="GBP",
        seller=seller,
        category=category,
        item_url=f"https://www.ebay.co.uk/itm/{item_id}",
        condition=condition,
        availability=availability,
        end_date=end_date,
    )


def test_scoring_is_deterministic_and_components_are_bounded():
    focus = get_current_search_focus(date(2026, 9, 5))
    assert focus is not None
    candidates = [
        listing("1", "Halloween pumpkin decor lights", "10.00"),
        listing("2", "Generic table lamp", "30.00"),
    ]
    scorer = MarketOpportunityScorer()

    first = scorer.score_candidates(candidates, focus)
    second = scorer.score_candidates(candidates, focus)

    assert first == second
    for result in first:
        assert set(result.component_scores) == {
            "seasonal_relevance",
            "price_attractiveness",
            "competition_density",
            "signal_quality",
            "data_completeness",
        }
        assert all(
            0 <= component <= 100
            for component in (
                result.seasonal_relevance,
                result.price_attractiveness,
                result.competition_density,
                result.signal_quality,
                result.data_completeness,
                result.overall_score,
            )
        )
        assert result.reasons[-1].endswith(f"{result.decision.value}.")
    assert first[0].overall_score > first[1].overall_score


def test_relative_price_competition_signals_and_completeness():
    focus = get_current_search_focus(date(2026, 9, 5))
    assert focus is not None
    complete = listing("cheap", "Pumpkin decor", "10.00")
    incomplete = listing(
        "expensive",
        "Pumpkin decor",
        "30.00",
        seller=None,
        condition=None,
        availability=None,
        end_date=None,
    )

    cheap_score, expensive_score = MarketOpportunityScorer().score_candidates(
        [complete, incomplete], focus
    )

    assert cheap_score.price_attractiveness == 100
    assert expensive_score.price_attractiveness == 0
    assert cheap_score.competition_density == expensive_score.competition_density == 85
    assert cheap_score.signal_quality == 100
    assert expensive_score.signal_quality == 15
    assert cheap_score.data_completeness == 100
    assert incomplete.category is not None
    assert expensive_score.data_completeness == 60


def test_decision_thresholds_are_fixed():
    scorer = MarketOpportunityScorer()

    assert scorer._decision(75) is OpportunityDecision.SHORTLIST
    assert scorer._decision(74) is OpportunityDecision.WATCH
    assert scorer._decision(50) is OpportunityDecision.WATCH
    assert scorer._decision(49) is OpportunityDecision.REJECT


def test_shortlist_returns_top_n_with_stable_ties():
    base = listing("b", "Candidate", "10.00")

    def scored(item_id, score):
        candidate = listing(item_id, "Candidate", "10.00")
        return ScoredMarketOpportunity(
            listing=candidate,
            seasonal_relevance=score,
            price_attractiveness=score,
            competition_density=score,
            signal_quality=score,
            data_completeness=score,
            overall_score=score,
            decision=OpportunityDecision.WATCH,
            reasons=(),
        )

    candidates = [scored(base.item_id, 70), scored("a", 70), scored("c", 90)]

    assert [item.listing.item_id for item in shortlist_candidates(candidates, 2)] == [
        "c",
        "a",
    ]
    assert shortlist_candidates(candidates, 0) == []
    with pytest.raises(ValueError, match="non-negative"):
        shortlist_candidates(candidates, -1)
