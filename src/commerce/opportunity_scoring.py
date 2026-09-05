import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum

from src.commerce.market_research import MarketListing
from src.commerce.seasonality import ProductSearchFocus


class OpportunityDecision(str, Enum):
    SHORTLIST = "SHORTLIST"
    WATCH = "WATCH"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ScoredMarketOpportunity:
    listing: MarketListing
    seasonal_relevance: int
    price_attractiveness: int
    competition_density: int
    signal_quality: int
    data_completeness: int
    overall_score: int
    decision: OpportunityDecision
    reasons: tuple[str, ...]

    @property
    def component_scores(self) -> dict[str, int]:
        return {
            "seasonal_relevance": self.seasonal_relevance,
            "price_attractiveness": self.price_attractiveness,
            "competition_density": self.competition_density,
            "signal_quality": self.signal_quality,
            "data_completeness": self.data_completeness,
        }


class MarketOpportunityScorer:
    """Deterministic scoring of normalized marketplace research results."""

    WEIGHTS = {
        "seasonal_relevance": 0.30,
        "price_attractiveness": 0.25,
        "competition_density": 0.15,
        "signal_quality": 0.15,
        "data_completeness": 0.15,
    }
    SHORTLIST_THRESHOLD = 75
    WATCH_THRESHOLD = 50

    def score_candidates(
        self,
        candidates: list[MarketListing],
        focus: ProductSearchFocus,
    ) -> list[ScoredMarketOpportunity]:
        comparable_keys = [self._comparable_key(item) for item in candidates]
        densities = Counter(comparable_keys)
        price_ranges = self._price_ranges(candidates)

        return [
            self._score_one(item, focus, densities, price_ranges)
            for item in candidates
        ]

    def _score_one(self, listing, focus, densities, price_ranges):
        seasonal = self._seasonal_relevance(listing, focus)
        price = self._price_attractiveness(listing, price_ranges)
        density_count = densities[self._comparable_key(listing)]
        competition = max(0, 100 - ((density_count - 1) * 15))
        signal = self._signal_quality(listing)
        completeness = self._data_completeness(listing)
        components = {
            "seasonal_relevance": seasonal,
            "price_attractiveness": price,
            "competition_density": competition,
            "signal_quality": signal,
            "data_completeness": completeness,
        }
        overall = _score(
            sum(components[name] * weight for name, weight in self.WEIGHTS.items())
        )
        decision = self._decision(overall)
        reasons = (
            f"Seasonal relevance {seasonal}/100 based on profile term overlap and priority.",
            f"Price attractiveness {price}/100 within same-currency results.",
            f"Competition score {competition}/100 across {density_count} comparable listing(s).",
            f"Seller/listing signal quality {signal}/100.",
            f"Data completeness {completeness}/100.",
            f"Overall score {overall}/100 results in {decision.value}.",
        )
        return ScoredMarketOpportunity(
            listing=listing,
            overall_score=overall,
            decision=decision,
            reasons=reasons,
            **components,
        )

    @staticmethod
    def _seasonal_relevance(listing, focus):
        listing_tokens = _tokens(f"{listing.title} {listing.category or ''}")
        keyword_overlap = max(
            (_overlap(listing_tokens, _tokens(term)) for term in focus.suggested_keywords),
            default=0.0,
        )
        category_overlap = max(
            (_overlap(listing_tokens, _tokens(term)) for term in focus.suggested_categories),
            default=0.0,
        )
        return _score(
            (keyword_overlap * 60)
            + (category_overlap * 30)
            + (focus.profile.priority_score * 0.10)
        )

    @staticmethod
    def _price_ranges(candidates):
        grouped = {}
        for listing in candidates:
            grouped.setdefault(
                MarketOpportunityScorer._comparable_key(listing), []
            ).append(listing.price)
        return {
            currency: (min(prices), max(prices))
            for currency, prices in grouped.items()
        }

    @staticmethod
    def _price_attractiveness(listing, price_ranges):
        low, high = price_ranges[MarketOpportunityScorer._comparable_key(listing)]
        if low == high:
            return 50
        return _score(float((high - listing.price) / (high - low)) * 100)

    @staticmethod
    def _signal_quality(listing):
        return (
            (35 if listing.seller else 0)
            + (25 if listing.condition else 0)
            + (25 if listing.availability else 0)
            + (15 if listing.item_url.startswith("https://") else 0)
        )

    @staticmethod
    def _data_completeness(listing):
        values = (
            listing.title,
            listing.item_id,
            listing.price,
            listing.currency,
            listing.seller,
            listing.category,
            listing.item_url,
            listing.condition,
            listing.availability,
            listing.end_date,
        )
        return _score(sum(value is not None and value != "" for value in values) * 10)

    @staticmethod
    def _comparable_key(listing):
        return (listing.currency, (listing.category or "uncategorized").casefold())

    def _decision(self, overall_score):
        if overall_score >= self.SHORTLIST_THRESHOLD:
            return OpportunityDecision.SHORTLIST
        if overall_score >= self.WATCH_THRESHOLD:
            return OpportunityDecision.WATCH
        return OpportunityDecision.REJECT


def shortlist_candidates(
    candidates: list[ScoredMarketOpportunity],
    top_n: int,
) -> list[ScoredMarketOpportunity]:
    """Return the top N scored candidates with deterministic tie-breaking."""
    if top_n < 0:
        raise ValueError("top_n must be non-negative")
    return sorted(
        candidates,
        key=lambda item: (-item.overall_score, item.listing.item_id),
    )[:top_n]


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _overlap(haystack: set[str], needles: set[str]) -> float:
    return len(haystack & needles) / len(needles) if needles else 0.0


def _score(value: float) -> int:
    return max(0, min(100, round(value)))
