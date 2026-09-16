from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.commerce.database import CommerceDatabase
from src.commerce.queue import CommerceQueue


def build_description(facts: dict) -> str:
    lines = [
        facts["ebay_title"],
        "",
        "Features:",
    ]

    for feature in facts.get("features", []):
        lines.append(f"- {feature}")

    lines.extend(
        [
            "",
            "Specifications:",
            f"- Material: {facts.get('material', 'Not specified')}",
            f"- Colour: {facts.get('colour', 'Not specified')}",
            f"- Size: {facts.get('dimensions', 'Not specified')}",
            f"- Weight: {facts.get('weight', 'Not specified')}",
            f"- Package: {facts.get('package', 'Not specified')}",
            "",
            "Package Includes:",
        ]
    )

    for item in facts.get("packing_list", []):
        lines.append(f"- {item}")

    if facts.get("notes"):
        lines.extend(["", "Please Note:"])
        for note in facts["notes"]:
            lines.append(f"- {note}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a buyer-safe eBay listing draft from verified supplier facts."
    )
    parser.add_argument("--sku", required=True)
    parser.add_argument("--db", default="data/commerce.db")
    parser.add_argument(
        "--facts",
        default="data/go_dropship_product_facts.json",
    )
    args = parser.parse_args()

    facts_path = Path(args.facts)
    facts_data = json.loads(facts_path.read_text())

    if args.sku not in facts_data:
        raise SystemExit(f"BLOCKED: no verified supplier facts for {args.sku}")

    facts = facts_data[args.sku]

    db = CommerceDatabase(args.db)

    candidates = [
        candidate
        for candidate in db.list_candidates(limit=10000)
        if candidate.sku == args.sku
    ]

    if not candidates:
        raise SystemExit(f"BLOCKED: no candidate found for {args.sku}")

    candidate = candidates[-1]

    description = build_description(facts)

    queue = CommerceQueue(db=db)

    draft = queue.create_ebay_draft(
        candidate_id=candidate.candidate_id,
        quantity=1,
        description=description,
        category=facts["ebay_category"],
        shipping=facts["shipping"],
    )

    print("=" * 60)
    print("AUTOMATED LISTING PREPARATION")
    print("=" * 60)
    print("SKU:", draft.sku)
    print("Draft:", draft.draft_id)
    print("Title:", draft.title)
    print("Price:", f"£{draft.price:.2f}")
    print("Quantity:", draft.quantity)
    print("Category:", draft.category)
    print("Shipping:", draft.shipping)
    print("Expected profit:", f"£{draft.expected_profit:.2f}")
    print("Expected margin:", f"{draft.expected_margin * 100:.2f}%")
    print("Status:", draft.status.value)
    print("Human approval required:", draft.human_approval_required)

    print("\nCUSTOMER DESCRIPTION")
    print("-" * 60)
    print(draft.description)

    print("\nIMAGE SOURCES")
    for url in facts.get("image_urls", []):
        print("-", url)

    print("\nSYSTEM RESULT: DRAFT PREPARED")
    print("NOT PUBLISHED")
    print("HUMAN REVIEW STILL REQUIRED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
