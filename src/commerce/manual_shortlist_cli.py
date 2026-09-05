"""Score a local JSON file of manually researched eBay candidates."""

import argparse
import json
import re
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

from src.commerce.market_research import MarketListing
from src.commerce.opportunity_scoring import (
    MarketOpportunityScorer,
    OpportunityDecision,
    shortlist_candidates,
)
from src.commerce.product_scout import get_current_search_focus
from src.commerce.shortlist_cli import _json_value


MIN_CANDIDATES = 5
MAX_CANDIDATES = 10


def _listing(raw: dict) -> MarketListing:
    if not isinstance(raw, dict):
        raise ValueError("Each candidate must be a JSON object.")
    values = dict(raw)
    try:
        values["price"] = Decimal(str(values["price"]))
        if values.get("end_date"):
            values["end_date"] = datetime.fromisoformat(values["end_date"])
        listing = MarketListing(**values)
    except (InvalidOperation, TypeError, KeyError) as exc:
        raise ValueError(f"Invalid candidate: {exc}") from exc

    if not listing.title.strip() or not listing.item_id.strip():
        raise ValueError("Candidate title and item_id must not be empty.")
    if listing.price <= 0:
        raise ValueError(f"Candidate {listing.item_id} price must be positive.")
    if not listing.currency.strip():
        raise ValueError(f"Candidate {listing.item_id} currency must not be empty.")
    hostname = (urlparse(listing.item_url).hostname or "").casefold()
    if not listing.item_url.startswith("https://") or not (
        re.fullmatch(r"(?:[a-z0-9-]+\.)*ebay\.[a-z]{2,}(?:\.[a-z]{2})?", hostname)
    ):
        raise ValueError(f"Candidate {listing.item_id} must have an HTTPS eBay item_url.")
    return listing


def load_manual_candidates(path: str | Path) -> list[MarketListing]:
    """Load and validate 5-10 offline eBay research records."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("candidates") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("Input must be a JSON array or an object with a candidates array.")
    if not MIN_CANDIDATES <= len(rows) <= MAX_CANDIDATES:
        raise ValueError("Manual shortlist input must contain 5 to 10 candidates.")
    listings = [_listing(row) for row in rows]
    item_ids = [listing.item_id for listing in listings]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("Candidate item_id values must be unique.")
    return listings


def score_manual_candidates(
    input_path: str | Path,
    output_path: str | Path = "shortlist.json",
    *,
    as_of: date | None = None,
) -> int:
    """Score local candidates and export eligible records for supplier verification."""
    listings = load_manual_candidates(input_path)
    focus = get_current_search_focus(as_of)
    if focus is None:
        raise ValueError("No seasonal product search focus is available for this date.")
    scored = MarketOpportunityScorer().score_candidates(listings, focus)
    eligible = [
        opportunity
        for opportunity in scored
        if opportunity.decision is OpportunityDecision.SHORTLIST
    ]
    shortlist = shortlist_candidates(eligible, MAX_CANDIDATES)
    Path(output_path).write_text(
        json.dumps([asdict(item) for item in shortlist], default=_json_value, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return len(shortlist)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Local JSON file containing 5-10 eBay candidates")
    parser.add_argument("--output", default="shortlist.json", help="Scored JSON output path")
    parser.add_argument(
        "--as-of", type=date.fromisoformat, help="Research date in YYYY-MM-DD format"
    )
    args = parser.parse_args(argv)
    try:
        count = score_manual_candidates(args.input, args.output, as_of=args.as_of)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Exported {count} scored eBay opportunities to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
