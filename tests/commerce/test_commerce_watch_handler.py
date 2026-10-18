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
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.commerce.schemas import (
    CandidateStatus,
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
        patch.object(
            _handler_mod,
            "find_active_candidate_approval",
            return_value=None,
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


# ---------------------------------------------------------------------------
# Tests: active human approval protection
# ---------------------------------------------------------------------------


class TestActiveApprovalProtection:
    """An active human approval must pause background agent re-processing."""

    def test_active_approval_skips_three_agent_pipeline(self):
        product = _make_pass_product("PET-AWAITING-APPROVAL")
        store = _build_fake_store([product])

        active_approval = {
            "approval_id": "approval-123",
            "candidate_id": "CAND-EBAY-PET-AWAITING-APPROVAL",
            "status": "PENDING",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "existing": True,
        }

        with (
            patch.dict(
                os.environ,
                {"COMMERCE_TABLE_NAME": "test-table"},
            ),
            patch.object(
                _handler_mod,
                "DynamoCommerceStore",
                return_value=store,
            ),
            patch.object(
                _handler_mod,
                "load_ebay_adapter",
                side_effect=RuntimeError("no ebay in tests"),
            ),
            patch.object(
                _handler_mod,
                "find_active_candidate_approval",
                return_value=active_approval,
            ),
            patch.object(
                _handler_mod.ThreeAgentPipeline,
                "run",
                side_effect=AssertionError(
                    "Three-agent pipeline must not run while approval is active"
                ),
            ),
        ):
            result = _handler_mod.lambda_handler({}, None)

        decision = result["decisions"][0]
        pipeline = decision["pipeline"]

        assert pipeline["skipped"] is True
        assert pipeline["approval_already_pending"] is True
        assert pipeline["approval_id"] == "approval-123"
        assert pipeline["human_approval_required"] is True
        assert pipeline["auto_approved"] is False
        assert pipeline["published"] is False

        assert (
            result["pipeline_counts"]["AWAITING_HUMAN_APPROVAL"]
            == 1
        )



class TestApprovedCandidatePublishApproval:
    """Approved candidates must go to final publish approval, never back through agents."""

    def test_approved_candidate_gets_fresh_publish_approval_without_agents(self):
        product = _make_pass_product("HB-PUBLISH-01")
        store = _build_fake_store([product])

        candidate_id = "CAND-EBAY-HB-PUBLISH-01"

        approved_candidate = SimpleNamespace(
            candidate_id=candidate_id,
            sku=product.supplier_sku,
            target_price=product.market_price,
            status=CandidateStatus.APPROVED_FOR_LISTING,
        )

        draft = SimpleNamespace(
            draft_id="DRAFT-EBAY-HB-PUBLISH-01",
        )

        listing_facts = {
            "ebay_category_id": "167137",
            "image_urls": [
                "https://www.godropship.co.uk/uploadfile/images/test-1.jpg"
            ],
        }

        publish_approval = {
            "approval_id": "publish-approval-123",
            "candidate_id": candidate_id,
            "draft_id": draft.draft_id,
            "sku": product.supplier_sku,
            "offer_id": "offer-123",
            "status": "PENDING_PUBLISH",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "review_url": "https://example.test/review?approval_id=publish-approval-123",
            "existing": False,
        }

        with (
            patch.dict(
                os.environ,
                {
                    "COMMERCE_TABLE_NAME": "test-table",
                    "APPROVAL_BASE_URL": "https://example.test/review",
                },
            ),
            patch.object(
                _handler_mod,
                "DynamoCommerceStore",
                return_value=store,
            ),
            patch.object(
                _handler_mod,
                "load_ebay_adapter",
                side_effect=RuntimeError("no ebay in tests"),
            ),
            patch.object(
                _handler_mod,
                "find_active_candidate_approval",
                return_value=None,
            ),
            patch.object(
                store,
                "get_candidate",
                return_value=approved_candidate,
            ),
            patch.object(
                store,
                "get_draft_by_candidate_id",
                return_value=draft,
            ),
            patch.object(
                _handler_mod.ListingFactsStore,
                "get",
                return_value=listing_facts,
            ),
            patch.object(
                _handler_mod,
                "load_access_token",
                return_value="fake-ebay-token",
            ),
            patch.object(
                _handler_mod,
                "prepare_offer",
                return_value={"offer_id": "offer-123"},
            ) as prepare_mock,
            patch.object(
                _handler_mod,
                "create_publish_approval",
                return_value=publish_approval,
            ) as publish_approval_mock,
            patch.object(
                _handler_mod,
                "create_candidate_approval",
                side_effect=AssertionError(
                    "First-stage approval must not be created "
                    "for an already-approved candidate"
                ),
            ),
            patch.object(
                _handler_mod.ThreeAgentPipeline,
                "run",
                side_effect=AssertionError(
                    "Three-agent pipeline must not rerun "
                    "for an already-approved candidate"
                ),
            ),
        ):
            result = _handler_mod.lambda_handler({}, None)

        pipeline = result["decisions"][0]["pipeline"]

        assert pipeline["approval_stage"] == "PUBLISH"
        assert pipeline["approval_request_created"] is True
        assert pipeline["approval_id"] == "publish-approval-123"
        assert pipeline["human_approval_required"] is True
        assert pipeline["auto_approved"] is False
        assert pipeline["published"] is False

        prepare_mock.assert_called_once()
        publish_approval_mock.assert_called_once()

        assert (
            result["pipeline_counts"]["AWAITING_PUBLISH_APPROVAL"]
            == 1
        )
        assert result["actions_taken"]["published"] is False

    def test_active_publish_approval_is_not_duplicated(self):
        product = _make_pass_product("HB-PUBLISH-ACTIVE")
        store = _build_fake_store([product])

        candidate_id = "CAND-EBAY-HB-PUBLISH-ACTIVE"

        approved_candidate = SimpleNamespace(
            candidate_id=candidate_id,
            sku=product.supplier_sku,
            target_price=product.market_price,
            status=CandidateStatus.APPROVED_FOR_LISTING,
        )

        active_approval = {
            "approval_id": "active-publish-123",
            "candidate_id": candidate_id,
            "status": "PENDING_PUBLISH",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "existing": True,
        }

        with (
            patch.dict(
                os.environ,
                {
                    "COMMERCE_TABLE_NAME": "test-table",
                    "APPROVAL_BASE_URL": "https://example.test/review",
                },
            ),
            patch.object(
                _handler_mod,
                "DynamoCommerceStore",
                return_value=store,
            ),
            patch.object(
                _handler_mod,
                "load_ebay_adapter",
                side_effect=RuntimeError("no ebay in tests"),
            ),
            patch.object(
                _handler_mod,
                "find_active_candidate_approval",
                return_value=active_approval,
            ),
            patch.object(
                store,
                "get_candidate",
                return_value=approved_candidate,
            ),
            patch.object(
                _handler_mod,
                "create_publish_approval",
                side_effect=AssertionError(
                    "A second publish approval must not be created"
                ),
            ),
            patch.object(
                _handler_mod,
                "prepare_offer",
                side_effect=AssertionError(
                    "Offer must not be rebuilt while a valid "
                    "publish approval is active"
                ),
            ),
            patch.object(
                _handler_mod.ThreeAgentPipeline,
                "run",
                side_effect=AssertionError(
                    "Three-agent pipeline must not rerun"
                ),
            ),
        ):
            result = _handler_mod.lambda_handler({}, None)

        pipeline = result["decisions"][0]["pipeline"]

        assert pipeline["approval_stage"] == "PUBLISH"
        assert pipeline["approval_already_pending"] is True
        assert pipeline["approval_id"] == "active-publish-123"
        assert pipeline["human_approval_required"] is True
        assert pipeline["auto_approved"] is False
        assert pipeline["published"] is False

        assert (
            result["pipeline_counts"]["AWAITING_PUBLISH_APPROVAL"]
            == 1
        )
        assert result["actions_taken"]["published"] is False
