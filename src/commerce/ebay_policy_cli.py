"""Discover and match existing eBay seller policies. This command is read-only on eBay."""

import argparse
import json

from src.commerce.database import CommerceDatabase
from src.commerce.ebay_policy_discovery import EBaySellerPolicyDiscovery
from src.commerce.policy_compatibility import match_supplier_to_ebay_policies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("supplier_id")
    parser.add_argument("--marketplace-id", default="EBAY_GB")
    parser.add_argument("--db", default="data/commerce.db")
    args = parser.parse_args(argv)

    db = CommerceDatabase(args.db)
    rules = db.get_supplier_policy_rules(args.supplier_id)
    if rules is None:
        parser.error(f"No persisted supplier rules for '{args.supplier_id}'.")
    snapshot = EBaySellerPolicyDiscovery().discover(args.marketplace_id)
    db.save_ebay_policy_snapshot(snapshot)
    result = match_supplier_to_ebay_policies(rules, snapshot)
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0 if result.status.value == "MATCHED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
