from datetime import date
from typing import Any, Optional

from src.commerce.market_research import MarketResearchService
from src.commerce.storage import CommerceStore
from src.commerce.opportunity_scoring import (
    MarketOpportunityScorer,
    ScoredMarketOpportunity,
    shortlist_candidates,
)
from src.commerce.schemas import (
    ProductCandidate,
    ProductLane,
    ScoutEvaluationResult,
    SupplierBackedProduct,
)
from src.commerce.seasonality import (
    DEFAULT_SEARCH_PROFILES,
    ProductSearchFocus,
    ProductSearchProfile,
    SeasonalOpportunity,
    SeasonalityCalendar,
    default_retail_events,
    get_top_seasonal_events,
)


class ProductScoutAgent:
    """
    Agent 1: Product Scout
    Discovers and evaluates commercial opportunities using supplier data,
    seasonal buying windows, category traits, and competition evidence.
    """

    def __init__(self, db: Optional[CommerceStore] = None):
        self.db = db

    def research_market(
        self,
        adapter,
        *,
        as_of: Optional[date] = None,
        limit_per_search: int = 20,
        top_n: int = 10,
    ) -> list[ScoredMarketOpportunity]:
        """
        Research the current actionable market focus using a read-only marketplace
        adapter, score opportunities deterministically, and return the best results.
        """
        focus = get_current_search_focus(as_of)
        if focus is None:
            return []

        service = MarketResearchService(adapter)
        listings = service.find_candidates(
            focus,
            limit_per_search=limit_per_search,
        )

        scored = MarketOpportunityScorer().score_candidates(listings, focus)
        return shortlist_candidates(scored, top_n)

    def evaluate(
        self,
        product: Any,
        as_of: Optional[date] = None,
        market_listings: Optional[list] = None,
    ) -> ScoutEvaluationResult:
        eval_date = as_of or date.today()

        # Extract product details
        if isinstance(product, SupplierBackedProduct):
            sku = product.supplier_sku
            title = product.product_name
            lane = product.lane
            market_price = product.market_price
        elif isinstance(product, ProductCandidate):
            sku = product.sku
            title = product.title
            lane = ProductLane.EVERGREEN
            market_price = product.target_price
        elif isinstance(product, dict):
            sku = product.get("supplier_sku") or product.get("sku", "UNKNOWN")
            title = product.get("product_name") or product.get("title", "Unknown Product")
            lane = product.get("lane", ProductLane.EVERGREEN)
            market_price = product.get("market_price") or product.get("target_price")
        else:
            sku = getattr(product, "supplier_sku", getattr(product, "sku", "UNKNOWN"))
            title = getattr(product, "product_name", getattr(product, "title", "Unknown Product"))
            lane = getattr(product, "lane", ProductLane.EVERGREEN)
            market_price = getattr(product, "market_price", getattr(product, "target_price", None))

        if isinstance(lane, str):
            lane = ProductLane(lane)

        reasons: list[str] = []
        matched_event: Optional[str] = None
        window_status: Optional[str] = None
        score = 75
        confidence = 0.80

        # Seasonality assessment
        calendar = SeasonalityCalendar(default_retail_events(eval_date))
        all_events = calendar.evaluate(eval_date, include_past_events=True)

        title_lower = title.lower()
        if lane == ProductLane.SEASONAL or any(e.event.name.lower() in title_lower or e.event.key in title_lower for e in all_events):
            # Find best matching event
            matched_opp = None
            for opp in all_events:
                if opp.event.name.lower() in title_lower or opp.event.key in title_lower:
                    matched_opp = opp
                    break
            if not matched_opp:
                top_open = calendar.top_events(eval_date, limit=1)
                matched_opp = top_open[0] if top_open else (all_events[0] if all_events else None)

            if matched_opp:
                matched_event = matched_opp.event.name
                window_status = matched_opp.window_status.value
                if matched_opp.window_status.value == "OPEN":
                    reasons.append(
                        f"Seasonal buying window for {matched_opp.event.name} is OPEN "
                        f"({matched_opp.days_until_window_end} days until window closes)."
                    )
                    score = 85
                elif matched_opp.window_status.value == "UPCOMING":
                    reasons.append(
                        f"Seasonal buying window for {matched_opp.event.name} is UPCOMING "
                        f"(opens in {matched_opp.days_until_window_start} days)."
                    )
                    score = 70
                else:
                    reasons.append(
                        f"Seasonal buying window for {matched_opp.event.name} is CLOSED "
                        f"({matched_opp.days_until_event} days until event date)."
                    )
                    score = 35
        else:
            window_status = "EVERGREEN"
            reasons.append("Evergreen product lane: steady year-round consumer demand.")
            score = 80

        # Competition and market listings assessment
        competition_density = 50
        if market_listings:
            competition_density = min(100, len(market_listings) * 15)
            confidence = 0.90
            reasons.append(f"Evaluated against {len(market_listings)} marketplace research listings.")
        elif market_price is not None:
            confidence = 0.85
            reasons.append(f"Validated marketplace price established at £{float(market_price):.2f}.")
        else:
            confidence = 0.50
            reasons.append("Marketplace sale price is pending independent confirmation.")

        # Recommendation synthesis
        if window_status == "CLOSED":
            recommendation = "REJECT"
            reasons.append("Scout recommendation: REJECT due to expired seasonal window.")
        elif score >= 75:
            recommendation = "PROCEED"
            reasons.append("Scout recommendation: PROCEED to commercial review.")
        else:
            recommendation = "WATCH"
            reasons.append("Scout recommendation: WATCH for optimal window or pricing.")

        return ScoutEvaluationResult(
            sku=sku,
            product_name=title,
            lane=lane,
            seasonal_event=matched_event,
            seasonal_window_status=window_status,
            competition_density=competition_density,
            confidence=confidence,
            score=score,
            recommendation=recommendation,
            reasons=reasons,
        )


def run(product: Any = None, *args: Any, **kwargs: Any) -> Any:
    if product is None:
        return "Product Scout not connected yet"
    return ProductScoutAgent().evaluate(product, *args, **kwargs)


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
