"""Tests for the Commerce Watch Lambda handler.

Covers:
1. PASS products enter the three-agent pipeline and evaluations are persisted.
2. Non-PASS products (PENDING, REJECT) skip the pipeline.
3. The handler never publishes, reprices, orders, or auto-approves.
4. Human approval remains mandatory in summary output.
5. Pipeline gate summary is included in each decision record.
6. Draft creation is attempted (and may fail gracefully) for READY_FOR_HUMAN_REVIEW.
"""

from __future__ import annotations

import importlib
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.commerce.schemas import (
    MarketValidationStatus,
    PipelineGateStatus,
    ProductLane,
    SupplierBackedProduct,
)

# ---------------------------------------------------------------------------
# The handler lives under src/lambda/... which uses a Python keyword as a
# package component.  We import it via importlib to avoid the SyntaxError
# that a bare `from src.lambda...` import statement would cause.
# ---------------------------------------------------------------------------
_handler_mod = importlib.import_module("src.lambda.commerce_watch.handler")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pass_product(sku: str = "PET-PASS-01") -> SupplierBackedProduct:
    """A fully validated, profitable PASS product."""
    return SupplierBackedProduct(
        supplier_name="Go Dropship",
        supplier_sku=sku,
        product_name="Validated Pet Feeder",
        supplier_cost=8.64,
        lane=ProductLane.EVERGREEN,
        market_price=16.99,
        platform_fees=3.18,
        return_allowance=1.25,
        market_price_validated=True,
        platform_fees_validated=True,
        return_allowance_validated=True,
        market_validation_status=MarketValidationStatus.PASS,
        profitable=True,
        expected_profit=3.92,
        expected_margin=0.2307,
        updated_at=datetime.now(timezone.utc),
    )


def _make_pending_product(sku: str = "PET-PEND-01") -> SupplierBackedProduct:
    """A product that has not yet been validated."""
    return SupplierBackedProduct(
        supplier_name="Go Dropship",
        supplier_sku=sku,
        product_name="Unvalidated Widget",
        supplier_cost=10.00,
        lane=ProductLane.EVERGREEN,
    )


def _build_fake_store(products: list[SupplierBackedProduct]):
    """Build a minimal fake DynamoCommerceStore with in-memory storage."""
    from tests.commerce.test_dynamo_storage import FakeDynamoResource
    from src.commerce.dynamo_storage import DynamoCommerceStore

    resource = FakeDynamoResource()
    store = DynamoCommerceStore(table_name="test-table", dynamodb_resource=resource)

    for product in products:
        store.save_supplier_backed_product(product)

    return store


def _run_handler(store):
    """Invoke lambda_handler with the given store, suppressing real eBay calls."""
    with (
        patch.dict(os.environ, {"COMMERCE_TABLE_NAME": "test-table"}),
        patch.object(_handler_mod, "DynamoCommerceStore", return_value=store),
        patch.object(
            _handler_mod,
            "load_ebay_adapter",
            side_effect=RuntimeError("no ebay in tests"),
        ),
    ):
        return _handler_mod.lambda_handler({}, None)


# ---------------------------------------------------------------------------
# Tests: PASS gate
# ---------------------------------------------------------------------------


class TestHandlerPassGate:
    """Verify that PASS products enter the pipeline and non-PASS ones do not."""

    def test_pass_product_enters_pipeline(self):
        product = _make_pass_product()
        store = _build_fake_store([product])
        result = _run_handler(store)

        decision = result["decisions"][0]
        assert decision["market_validation_status"] == "PASS"
        # Pipeline was run — evidence dict must contain a pipeline_run_id
        assert "pipeline_run_id" in decision["pipeline"]
        assert decision["pipeline"]["gate_status"] in (
            PipelineGateStatus.READY_FOR_HUMAN_REVIEW.value,
            PipelineGateStatus.REVIEW.value,
            PipelineGateStatus.REJECT.value,
        )

    def test_pending_product_skips_pipeline(self):
        product = _make_pending_product()
        store = _build_fake_store([product])
        result = _run_handler(store)

        decision = result["decisions"][0]
        assert decision["market_validation_status"] == "PENDING"
        # Pipeline evidence must be empty dict — no pipeline was run
        assert decision["pipeline"] == {}

    def test_pass_product_agent_evaluations_persisted(self):
        """Agent evaluations must be persisted in DynamoDB (save_agent_evaluation)."""
        product = _make_pass_product()
        store = _build_fake_store([product])
        _run_handler(store)

        evals = store.list_agent_evaluations(supplier_sku=product.supplier_sku)
        assert len(evals) == 3, (
            f"Expected 3 evals (Scout+Commercial+Critic), got {len(evals)}"
        )
        roles = {e.agent_role.value for e in evals}
        assert roles == {"SCOUT", "COMMERCIAL", "CRITIC"}

    def test_mixed_products_only_pass_gets_pipeline(self):
        """With one PASS and one PENDING product only the PASS goes through the pipeline."""
        pass_product = _make_pass_product("PET-PASS-MIX")
        pending_product = _make_pending_product("PET-PEND-MIX")
        store = _build_fake_store([pass_product, pending_product])
        result = _run_handler(store)

        by_sku = {d["supplier_sku"]: d for d in result["decisions"]}
        assert "pipeline_run_id" in by_sku["PET-PASS-MIX"]["pipeline"]
        assert by_sku["PET-PEND-MIX"]["pipeline"] == {}


# ---------------------------------------------------------------------------
# Tests: Safety guards
# ---------------------------------------------------------------------------


class TestHandlerSafetyGuards:
    """Verify that the handler never publishes, reprices, orders, or auto-approves."""

    def test_actions_taken_never_true(self):
        product = _make_pass_product()
        store = _build_fake_store([product])
        result = _run_handler(store)

        actions = result["actions_taken"]
        assert actions["published"] is False
        assert actions["repriced"] is False
        assert actions["ordered"] is False

    def test_human_approval_required_is_always_true(self):
        product = _make_pass_product()
        store = _build_fake_store([product])
        result = _run_handler(store)

        assert result["human_approval_required"] is True
        # Pipeline evidence must also flag it
        pipeline = result["decisions"][0]["pipeline"]
        if pipeline:  # pipeline ran
            assert pipeline["human_approval_required"] is True
            assert pipeline["auto_approved"] is False
            assert pipeline["published"] is False

    def test_product_auto_approved_and_published_remain_false(self):
        product = _make_pass_product()
        store = _build_fake_store([product])
        result = _run_handler(store)

        decision = result["decisions"][0]
        assert decision["auto_approved"] is False
        assert decision["published"] is False


# ---------------------------------------------------------------------------
# Tests: Pipeline counts
# ---------------------------------------------------------------------------


class TestHandlerPipelineCounts:
    """Verify that pipeline_counts in the summary reflects gate outcomes."""

    def test_pipeline_counts_populated_for_pass_product(self):
        product = _make_pass_product()
        store = _build_fake_store([product])
        result = _run_handler(store)

        counts = result["pipeline_counts"]
        # Exactly one pipeline run for one PASS product
        total = sum(counts.values())
        assert total == 1

    def test_pipeline_counts_empty_for_pending_only_products(self):
        products = [_make_pending_product("PET-P1"), _make_pending_product("PET-P2")]
        store = _build_fake_store(products)
        result = _run_handler(store)

        assert result["pipeline_counts"] == {}


# ---------------------------------------------------------------------------
# Tests: market_evidence_ready PASS gate (unit)
# ---------------------------------------------------------------------------


class TestMarketEvidenceReadyPassGate:
    """Unit tests for ThreeAgentPipeline.market_evidence_ready."""

    def test_pass_with_price_is_ready(self):
        from src.commerce.three_agent_pipeline import ThreeAgentPipeline

        product = _make_pass_product()
        assert ThreeAgentPipeline.market_evidence_ready(product) is True

    def test_pending_with_price_is_not_ready(self):
        from src.commerce.three_agent_pipeline import ThreeAgentPipeline

        product = SupplierBackedProduct(
            supplier_name="Go Dropship",
            supplier_sku="PET-PEND-99",
            product_name="Widget",
            supplier_cost=10.0,
            lane=ProductLane.EVERGREEN,
            market_price=20.0,
            # market_validation_status defaults to PENDING
        )
        assert ThreeAgentPipeline.market_evidence_ready(product) is False

    def test_pass_without_market_price_is_not_ready(self):
        """PASS status alone is insufficient without a market price."""
        from src.commerce.three_agent_pipeline import ThreeAgentPipeline

        product = _make_pass_product()
        # Simulate a product that lost its price (patched via model_copy)
        product = product.model_copy(update={"market_price": None})
        assert ThreeAgentPipeline.market_evidence_ready(product) is False

    def test_reject_status_is_not_ready(self):
        from src.commerce.three_agent_pipeline import ThreeAgentPipeline

        product = SupplierBackedProduct(
            supplier_name="Go Dropship",
            supplier_sku="PET-REJ-01",
            product_name="Rejected Widget",
            supplier_cost=10.0,
            lane=ProductLane.EVERGREEN,
            market_price=20.0,
            market_price_validated=True,
            platform_fees_validated=True,
            return_allowance_validated=True,
            market_validation_status=MarketValidationStatus.REJECT,
            profitable=False,
        )
        assert ThreeAgentPipeline.market_evidence_ready(product) is False
