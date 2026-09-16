"""CLI tool to execute the 3-agent commerce pipeline over staged supplier products."""

import argparse
from datetime import date
import sys
from typing import Sequence

from src.commerce.database import CommerceDatabase
from src.commerce.schemas import PipelineGateStatus
from src.commerce.three_agent_pipeline import ThreeAgentPipeline


def print_run_result(result) -> None:
    sep = "=" * 80
    sub = "-" * 80
    print(sep)
    print(f"Pipeline Run: {result.pipeline_run_id} | SKU: {result.supplier_sku} ({result.supplier_name})")
    print(sub)
    print(f"Product: {result.scout_eval.product_name} ({result.scout_eval.lane.value})")

    # Scout details
    print(f"\n[Agent 1 - Scout]: Score: {result.scout_eval.score}/100 | "
          f"Confidence: {result.scout_eval.confidence:.0%} | "
          f"Rec: {result.scout_eval.recommendation}")
    for reason in result.scout_eval.reasons:
        print(f"  • {reason}")

    # Commercial details
    comm = result.commercial_eval
    print(f"\n[Agent 2 - Commercial]: Rec: {comm.recommendation}")
    print(f"  • Proposed Price: £{comm.proposed_price:.2f} | Supplier Cost: £{comm.supplier_cost:.2f}")
    print(f"  • Platform Fees: £{comm.platform_fee:.2f} | Return Buffer: £{comm.return_buffer:.2f}")
    print(f"  • Net Profit: £{comm.expected_profit:.2f} | Margin: {comm.expected_margin:.2%} "
          f"({'PASS' if comm.meets_minimum_margin else 'FAIL'} min 20%)")
    print(f"  • Sourcing Valid: {comm.supplier_valid} | Policy Compatible: {comm.policy_compatible}")

    # Critic details
    crit = result.critic_eval
    print(f"\n[Agent 3 - Critic]: Rec: {crit.recommendation.value} | Risk Score: {crit.risk_score}/100")
    print(f"  • Margin Cushion: {crit.margin_cushion:+.2%}")
    if crit.stress_test_results:
        m5 = crit.stress_test_results.get("price_minus_5pct_margin")
        if m5 is not None:
            print(f"  • Stress Test (-5% Price): margin {m5:.2%}")
        ms = crit.stress_test_results.get("shipping_plus_1gbp_margin")
        if ms is not None:
            print(f"  • Stress Test (+£1 Shipping): margin {ms:.2%}")
    if crit.risk_flags:
        print("  • Risk Flags:")
        for flag in crit.risk_flags:
            print(f"    - {flag}")

    # Deterministic Gate
    print(f"\n{sub}")
    print(f"DETERMINISTIC GATE DECISION: {result.gate_status.value}")
    print(f"Queue Status: {result.queue_status.value} (Candidate ID: {result.candidate_id})")
    print("Safety Invariants: auto_approved=False | published=False | human_approval_required=True")
    print(f"Outcome Reason: {result.reasons[-1]}")
    print(sep)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run 3-agent commerce pipeline over staged supplier products."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sku", help="Supplier SKU to evaluate (e.g. PET-73110)")
    group.add_argument("--all", action="store_true", help="Evaluate all staged supplier products")
    parser.add_argument("--supplier", default="Go Dropship", help="Supplier name (default: Go Dropship)")
    parser.add_argument("--db", default="data/commerce.db", help="SQLite database path")
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="Evaluation date in YYYY-MM-DD format (default: today)",
    )
    args = parser.parse_args(argv)

    db = CommerceDatabase(args.db)
    pipeline = ThreeAgentPipeline(db=db)

    try:
        if args.sku:
            result = pipeline.run_for_sku(
                supplier_sku=args.sku,
                supplier_name=args.supplier,
                as_of=args.as_of,
            )
            print_run_result(result)
        else:
            results = pipeline.run_staged_batch(as_of=args.as_of)
            for res in results:
                print_run_result(res)
            print(f"\nBatch completed: {len(results)} staged product(s) evaluated through 3-agent pipeline.")
            print("Zero listings auto-approved. Zero listings published. Human approval is mandatory.")
    except Exception as exc:
        print(f"Error running pipeline: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
