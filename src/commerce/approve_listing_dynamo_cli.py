"""Explicit human approval and DynamoDB eBay draft creation.

Lifecycle:
REVIEW
-> explicit human approval
-> APPROVED_FOR_LISTING
-> DRAFT_CREATED
-> stop

This command NEVER publishes an eBay listing.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.prepare_listing_cli import build_description
from src.commerce.queue import CandidateQueue
from src.commerce.schemas import CandidateStatus


DEFAULT_TABLE_NAME = "3-trading-agents-commerce-v1"
DEFAULT_REGION = "eu-west-2"
DEFAULT_FACTS_PATH = "data/go_dropship_product_facts.json"


def approve_and_create_draft(
    *,
    candidate_id: str,
    reviewer: str,
    table_name: str,
    region_name: str,
    facts_path: str,
):
    store = DynamoCommerceStore(
        table_name=table_name,
        region_name=region_name,
    )

    queue = CandidateQueue(db=store)

    candidate = queue.get_candidate(candidate_id)

    if candidate is None:
        raise ValueError(
            f"Candidate '{candidate_id}' was not found."
        )

    if candidate.status is not CandidateStatus.REVIEW:
        raise ValueError(
            "Candidate cannot be approved from status "
            f"{candidate.status.value}; expected REVIEW."
        )

    path = Path(facts_path)

    if not path.exists():
        raise ValueError(
            f"Verified supplier facts file not found: {facts_path}"
        )

    facts_data = json.loads(path.read_text())

    if candidate.sku not in facts_data:
        raise ValueError(
            "BLOCKED: no verified supplier facts for "
            f"{candidate.sku}."
        )

    facts = facts_data[candidate.sku]

    required = (
        "ebay_title",
        "features",
        "material",
        "dimensions",
        "packing_list",
        "ebay_category",
        "shipping",
    )

    missing = [
        key
        for key in required
        if not facts.get(key)
    ]

    if missing:
        raise ValueError(
            "BLOCKED: supplier facts are incomplete: "
            + ", ".join(missing)
        )

    # Build customer-facing text BEFORE changing candidate status.
    # If facts are invalid, no approval is recorded.
    description = build_description(facts)

    approved = queue.approve_for_listing(
        candidate_id=candidate_id,
        reviewer=reviewer,
        notes=(
            "Explicit human approval after market validation "
            "and three-agent review."
        ),
    )

    if approved.status is not CandidateStatus.APPROVED_FOR_LISTING:
        raise RuntimeError(
            "Candidate did not reach APPROVED_FOR_LISTING."
        )

    draft = queue.create_ebay_draft(
        candidate_id=candidate_id,
        quantity=1,
        description=description,
        category=facts["ebay_category"],
        shipping=facts["shipping"],
    )

    return approved, draft, facts


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Explicitly approve one REVIEW candidate and create "
            "a verified eBay draft in DynamoDB. Never publishes."
        )
    )

    parser.add_argument(
        "--candidate-id",
        required=True,
    )

    parser.add_argument(
        "--reviewer",
        required=True,
    )

    parser.add_argument(
        "--approve",
        action="store_true",
        help="Required explicit human approval flag.",
    )

    parser.add_argument(
        "--facts",
        default=DEFAULT_FACTS_PATH,
    )

    parser.add_argument(
        "--table",
        default=os.environ.get(
            "COMMERCE_TABLE_NAME",
            DEFAULT_TABLE_NAME,
        ),
    )

    parser.add_argument(
        "--region",
        default=os.environ.get(
            "AWS_REGION",
            DEFAULT_REGION,
        ),
    )

    args = parser.parse_args()

    if not args.approve:
        raise SystemExit(
            "BLOCKED: explicit --approve flag is required. "
            "Nothing was changed."
        )

    approved, draft, facts = approve_and_create_draft(
        candidate_id=args.candidate_id,
        reviewer=args.reviewer,
        table_name=args.table,
        region_name=args.region,
        facts_path=args.facts,
    )

    print("=" * 60)
    print("HUMAN APPROVAL RECORDED")
    print("=" * 60)
    print("Candidate:", approved.candidate_id)
    print("Candidate status:", approved.status.value)
    print("SKU:", draft.sku)
    print("Draft:", draft.draft_id)
    print("Draft status:", draft.status.value)
    print("Title:", draft.title)
    print("Price:", f"£{draft.price:.2f}")
    print("Category:", draft.category)
    print("Shipping:", draft.shipping)
    print("Expected profit:", f"£{draft.expected_profit:.2f}")
    print(
        "Expected margin:",
        f"{draft.expected_margin * 100:.2f}%",
    )
    print("Verified supplier facts: True")
    print("Image count:", len(facts.get("image_urls", [])))
    print("Human approval required before publish: True")
    print("Published: False")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
