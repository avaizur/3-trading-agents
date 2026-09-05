"""Export top scored eBay research opportunities for manual verification."""

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from src.commerce.adapters.ebay_browse import EBayBrowseResearchAdapter
from src.commerce.adapters.market_research import MarketResearchAdapter
from src.commerce.market_research import MarketResearchService
from src.commerce.opportunity_scoring import (
    MarketOpportunityScorer,
    OpportunityDecision,
    shortlist_candidates,
)
from src.commerce.product_scout import get_current_search_focus


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def export_shortlist(
    adapter: MarketResearchAdapter,
    output_path: str | Path = "shortlist.json",
    *,
    top_n: int = 10,
    limit_per_search: int = 20,
    as_of: date | None = None,
) -> int:
    """Research, score, and export eBay shortlist decisions without marketplace writes."""
    if not 5 <= top_n <= 10:
        raise ValueError("top_n must be between 5 and 10")

    focus = get_current_search_focus(as_of)
    if focus is None:
        raise ValueError("No seasonal product search focus is available for this date.")

    listings = MarketResearchService(adapter).find_candidates(
        focus, limit_per_search=limit_per_search
    )
    scored = MarketOpportunityScorer().score_candidates(listings, focus)
    eligible = [
        opportunity
        for opportunity in scored
        if opportunity.decision is OpportunityDecision.SHORTLIST
    ]
    shortlist = shortlist_candidates(eligible, top_n)
    payload = [asdict(opportunity) for opportunity in shortlist]
    Path(output_path).write_text(
        json.dumps(payload, default=_json_value, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(shortlist)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", default="shortlist.json", help="Local JSON output path"
    )
    parser.add_argument(
        "--top", type=int, default=10, choices=range(5, 11), metavar="5-10"
    )
    parser.add_argument(
        "--limit-per-search", type=int, default=20, choices=range(1, 201)
    )
    parser.add_argument(
        "--as-of", type=date.fromisoformat, help="Research date in YYYY-MM-DD format"
    )
    args = parser.parse_args(argv)

    try:
        count = export_shortlist(
            EBayBrowseResearchAdapter(),
            args.output,
            top_n=args.top,
            limit_per_search=args.limit_per_search,
            as_of=args.as_of,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Exported {count} eBay opportunities to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
