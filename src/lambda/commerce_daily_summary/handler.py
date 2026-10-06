from __future__ import annotations

from typing import Any


def _payload(event: dict[str, Any], *path: str) -> dict[str, Any]:
    current: Any = event

    for key in path:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)

    return current if isinstance(current, dict) else {}


def _money(value: Any) -> str:
    try:
        return f"£{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _margin(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def build_summary(event: dict[str, Any]) -> dict[str, str]:
    discovery = _payload(event, "discovery", "Payload")
    watch = _payload(event, "watch", "watch")
    replenishment = _payload(event, "replenishment", "replenishment")

    watch_counts = watch.get("watch_counts") or {}
    pipeline_counts = watch.get("pipeline_counts") or {}
    decisions = watch.get("decisions") or []
    replenishment_results = replenishment.get("results") or []

    approvals: list[dict[str, Any]] = []

    for decision in decisions:
        if not isinstance(decision, dict):
            continue

        pipeline = decision.get("pipeline") or {}

        if (
            pipeline.get("approval_request_created") is True
            and pipeline.get("approval_url")
        ):
            approvals.append(
                {
                    "sku": decision.get("supplier_sku", "UNKNOWN"),
                    "name": decision.get("product_name", "Unnamed product"),
                    "market_price": decision.get("market_price"),
                    "profit": decision.get("expected_profit"),
                    "margin": decision.get("expected_margin"),
                    "url": pipeline["approval_url"],
                }
            )

    blocked = [
        item
        for item in replenishment_results
        if isinstance(item, dict)
        and item.get("status") in {"BLOCKED", "ERROR"}
    ]

    subject = (
        f"3 Trading Agents - {len(approvals)} "
        f"approval{'s' if len(approvals) != 1 else ''} waiting"
    )

    lines = [
        "3 Trading Agents - Daily Commerce Review",
        "",
        "SUMMARY",
        f"Products discovered: {discovery.get('discovered', 0)}",
        f"New supplier products imported: {discovery.get('imported', 0)}",
        f"Market PASS: {watch_counts.get('PASS', 0)}",
        f"Market REJECT: {watch_counts.get('REJECT', 0)}",
        f"Needs refresh: {watch_counts.get('NEEDS_REFRESH', 0)}",
        (
            "Ready for human review: "
            f"{pipeline_counts.get('READY_FOR_HUMAN_REVIEW', 0)}"
        ),
        f"Caution / review: {pipeline_counts.get('REVIEW', 0)}",
        f"Already live: {pipeline_counts.get('ALREADY_LIVE', 0)}",
        "",
        f"ACTIONABLE APPROVALS: {len(approvals)}",
    ]

    if approvals:
        for approval in approvals:
            lines.extend(
                [
                    "",
                    f"{approval['sku']} - {approval['name']}",
                    (
                        f"Market price: {_money(approval['market_price'])} | "
                        f"Expected profit: {_money(approval['profit'])} | "
                        f"Margin: {_margin(approval['margin'])}"
                    ),
                    f"Review / Approve: {approval['url']}",
                ]
            )
    else:
        lines.append("No new approval links require action today.")

    lines.extend(
        [
            "",
            "LIVE LISTING MONITORING",
            f"Live listings checked: {replenishment.get('checked', 0)}",
        ]
    )

    for item in replenishment_results:
        if not isinstance(item, dict):
            continue

        status = item.get("status", "UNKNOWN")
        sku = item.get("sku", "UNKNOWN")

        if status == "IN_STOCK":
            lines.append(f"{sku}: In stock")
        elif status in {"BLOCKED", "ERROR"}:
            lines.append(
                f"{sku}: WARNING - {status}: "
                f"{item.get('reason', 'No reason supplied')}"
            )
        elif status == "DRY_RUN_REPLENISH":
            lines.append(f"{sku}: Would replenish after safety checks")
        elif item.get("replenished"):
            lines.append(f"{sku}: Replenished safely to quantity 1")
        else:
            lines.append(f"{sku}: {status}")

    lines.extend(
        [
            "",
            "SAFETY",
            "No automatic supplier orders were placed.",
            "No product was automatically published without human approval.",
        ]
    )

    if blocked:
        lines.extend(
            [
                "",
                (
                    f"Attention: {len(blocked)} live listing"
                    f"{'s' if len(blocked) != 1 else ''} "
                    "could not be safely replenished."
                ),
            ]
        )

    return {
        "subject": subject,
        "message": "\n".join(lines),
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    del context
    return build_summary(event)
