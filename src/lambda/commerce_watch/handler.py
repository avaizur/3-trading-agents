"""Daily Commerce Watch Lambda.

Reads supplier-backed products from DynamoDB, refreshes stale/missing
market evidence from eBay, applies the deterministic profit gate when
all economics are available, and persists a watch-run summary.

For products whose market_validation_status is PASS, the three-agent
pipeline (Scout -> Seller/Commercial -> Critic) is run and agent
evaluations are persisted in DynamoDB.

A successful three-agent result stops at READY_FOR_HUMAN_REVIEW.
Human approval is required before a candidate can move to
APPROVED_FOR_LISTING and before an eBay draft can be created.

Safety:
- never auto-approves
- never creates a draft before human candidate approval
- never publishes
- never reprices marketplace listings
- never places supplier orders
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.live_market_refresh import (
    load_ebay_adapter,
    refresh_product_market,
)
from src.commerce.schemas import MarketValidationStatus, PipelineGateStatus
from src.commerce.three_agent_pipeline import ThreeAgentPipeline


MARKET_EVIDENCE_MAX_AGE = timedelta(hours=24)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _watch_status(product, now: datetime) -> tuple[str, str]:
    validations_complete = all(
        (
            product.market_price_validated,
            product.platform_fees_validated,
            product.return_allowance_validated,
        )
    )

    if not validations_complete:
        return (
            "NEEDS_REFRESH",
            "Market price, platform fees, or return allowance needs validation.",
        )

    if product.updated_at is None:
        return (
            "NEEDS_REFRESH",
            "No market evidence timestamp is available.",
        )

    updated_at = product.updated_at

    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    age = now - updated_at.astimezone(timezone.utc)

    if age > MARKET_EVIDENCE_MAX_AGE:
        return (
            "NEEDS_REFRESH",
            "Market evidence is older than 24 hours.",
        )

    return (
        product.market_validation_status.value,
        "Existing market validation is still current.",
    )


def _to_dynamo(value):
    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, list):
        return [_to_dynamo(item) for item in value]

    if isinstance(value, dict):
        return {
            key: _to_dynamo(item)
            for key, item in value.items()
        }

    return value


def lambda_handler(event, context):
    now = _utc_now()
    run_id = uuid4().hex[:12]
    watch_run_id = f"WATCH#{run_id}"

    table_name = os.environ["COMMERCE_TABLE_NAME"]
    aws_region = os.environ.get("AWS_REGION", "eu-west-2")
    ebay_secret_id = os.environ.get(
        "EBAY_SECRET_ID",
        "3-trading-agents/ebay-production",
    )

    store = DynamoCommerceStore(
        table_name=table_name,
        region_name=aws_region,
    )

    pipeline = ThreeAgentPipeline(db=store)

    products = store.list_supplier_backed_products()

    supplier_counts = Counter()
    watch_counts = Counter()
    refresh_counts = Counter()
    pipeline_counts = Counter()

    decisions = []
    adapter = None

    for product in products:
        supplier_counts[product.supplier_name] += 1

        initial_status, initial_reason = _watch_status(
            product=product,
            now=now,
        )

        refresh_evidence = {
            "attempted": False,
            "refreshed": False,
        }

        if initial_status == "NEEDS_REFRESH":
            refresh_evidence["attempted"] = True

            try:
                if adapter is None:
                    adapter = load_ebay_adapter(ebay_secret_id)

                refreshed_product, evidence = refresh_product_market(
                    product=product,
                    adapter=adapter,
                )

                refresh_evidence.update(evidence)

                if evidence.get("refreshed"):
                    store.save_supplier_backed_product(refreshed_product)
                    product = refreshed_product
                    refresh_counts["REFRESHED"] += 1
                else:
                    refresh_counts["NO_COMPARABLES"] += 1

            except Exception as exc:
                refresh_counts["ERROR"] += 1
                refresh_evidence.update(
                    {
                        "refreshed": False,
                        "reason": (
                            "Live market refresh failed: "
                            f"{type(exc).__name__}"
                        ),
                    }
                )

        watch_status, reason = _watch_status(
            product=product,
            now=now,
        )

        if (
            watch_status == "NEEDS_REFRESH"
            and refresh_evidence.get("attempted")
            and not refresh_evidence.get("refreshed")
        ):
            reason = refresh_evidence.get(
                "reason",
                initial_reason,
            )

        watch_counts[watch_status] += 1

        # --------------------------------------------------------------
        # Three-agent pipeline
        #
        # Only products that have passed deterministic market/economics
        # validation are allowed into Scout -> Commercial -> Critic.
        # --------------------------------------------------------------
        pipeline_evidence: dict = {}

        if (
            product.market_validation_status
            is MarketValidationStatus.PASS
            and ThreeAgentPipeline.market_evidence_ready(product)
        ):
            try:
                pipeline_result = pipeline.run(
                    product=product,
                    target_price=product.market_price,
                    platform_fee=product.platform_fees,
                    return_allowance=product.return_allowance,
                    persist_history=True,
                )

                gate_value = pipeline_result.gate_status.value

                pipeline_evidence = {
                    "pipeline_run_id": (
                        pipeline_result.pipeline_run_id
                    ),
                    "gate_status": gate_value,
                    "queue_status": (
                        pipeline_result.queue_status.value
                    ),
                    "scout_recommendation": (
                        pipeline_result.scout_eval.recommendation
                    ),
                    "commercial_margin": (
                        pipeline_result
                        .commercial_eval
                        .expected_margin
                    ),
                    "critic_recommendation": (
                        pipeline_result
                        .critic_eval
                        .recommendation
                        .value
                    ),
                    "reasons": pipeline_result.reasons,
                    "auto_approved": False,
                    "published": False,
                    "human_approval_required": True,
                }

                pipeline_counts[gate_value] += 1

                # IMPORTANT:
                # READY_FOR_HUMAN_REVIEW is intentionally the end of
                # automatic processing.
                #
                # Existing lifecycle:
                #
                # READY_FOR_HUMAN_REVIEW
                # -> human approve_for_listing()
                # -> APPROVED_FOR_LISTING
                # -> create_ebay_draft()
                # -> separate human approval before publish
                #
                # Do not create the draft here.
                if (
                    pipeline_result.gate_status
                    is PipelineGateStatus.READY_FOR_HUMAN_REVIEW
                ):
                    pipeline_evidence["draft_created"] = False
                    pipeline_evidence[
                        "human_review_required"
                    ] = True

            except Exception as pipeline_exc:
                pipeline_counts["ERROR"] += 1

                pipeline_evidence = {
                    "error": (
                        "Pipeline failed: "
                        f"{type(pipeline_exc).__name__}"
                    ),
                    "auto_approved": False,
                    "published": False,
                    "human_approval_required": True,
                }

        decisions.append(
            {
                "supplier_name": product.supplier_name,
                "supplier_sku": product.supplier_sku,
                "product_name": product.product_name,
                "market_validation_status": (
                    product.market_validation_status.value
                ),
                "watch_status": watch_status,
                "reason": reason,
                "profitable": product.profitable,
                "expected_profit": product.expected_profit,
                "expected_margin": product.expected_margin,
                "market_price": product.market_price,
                "refresh": refresh_evidence,
                "pipeline": pipeline_evidence,
                "auto_approved": product.auto_approved,
                "published": product.published,
            }
        )

    summary = {
        "watch_run_id": watch_run_id,
        "started_at": now.isoformat(),
        "product_count": len(products),
        "supplier_counts": dict(supplier_counts),
        "watch_counts": dict(watch_counts),
        "refresh_counts": dict(refresh_counts),
        "pipeline_counts": dict(pipeline_counts),
        "decisions": decisions,
        "actions_taken": {
            "published": False,
            "repriced": False,
            "ordered": False,
        },
        "human_approval_required": True,
    }

    store.table.put_item(
        Item=_to_dynamo(
            {
                "PK": f"WATCH_RUN#{run_id}",
                "SK": "SUMMARY",
                "entity_type": "COMMERCE_WATCH_RUN",
                **summary,
            }
        )
    )

    return {
        "ok": True,
        "table": table_name,
        **summary,
    }
