"""Persist supplier operational policy rules locally for marketplace matching."""

import argparse

from src.commerce.database import CommerceDatabase
from src.commerce.schemas import (
    ReturnPostagePayer,
    ReturnRoute,
    SupplierPolicyRules,
)


def _yes_no(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"y", "yes", "true", "1"}:
        return True
    if normalized in {"n", "no", "false", "0"}:
        return False
    raise argparse.ArgumentTypeError("enter yes or no")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("supplier_id")
    parser.add_argument("--dispatch-time-days", type=int, required=True)
    parser.add_argument("--shipping-service", action="append", required=True)
    parser.add_argument("--remote-surcharge", type=float, default=0.0)
    parser.add_argument("--blind-ship", type=_yes_no, required=True)
    parser.add_argument(
        "--return-route",
        choices=[item.value for item in ReturnRoute],
        required=True,
    )
    parser.add_argument("--rma-required", type=_yes_no, required=True)
    parser.add_argument(
        "--return-postage",
        choices=[item.value for item in ReturnPostagePayer],
        required=True,
    )
    parser.add_argument("--db", default="data/commerce.db")
    args = parser.parse_args(argv)

    rules = SupplierPolicyRules(
        supplier_id=args.supplier_id,
        dispatch_time_days=args.dispatch_time_days,
        shipping_services=args.shipping_service,
        remote_surcharge=args.remote_surcharge,
        blind_ship=args.blind_ship,
        return_route=ReturnRoute(args.return_route),
        rma_required=args.rma_required,
        return_postage=ReturnPostagePayer(args.return_postage),
    )

    CommerceDatabase(args.db).save_supplier_policy_rules(rules)
    print(f"Supplier policy rules saved for {args.supplier_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
