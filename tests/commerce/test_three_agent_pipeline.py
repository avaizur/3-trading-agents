"""Tests for the 3-agent commerce pipeline.

Covers:
  1. Profitable PASS product (Scout -> Commercial -> Critic -> Review)
  2. Low-margin REJECT (Deterministic safety gate rejection)
  3. Critic CAUTION (Risk flags, thin margin cushion)
  4. Critic BLOCK (Closed season, non-blind shipping)
  5. History persistence (agent_evaluations, human_decisions, realized_outcomes)
  6. Human gate & no auto-publish (strictly mandatory human approval)
  7. Learning history cannot alter the 20% minimum margin threshold
"""

from datetime import date, datetime, timezone
import pytest

from src.commerce.adapters.ebay import EBayAdapter
from src.commerce.database import CommerceDatabase
from src.commerce.profit_engine import DEFAULT_MIN_MARGIN_PCT
from src.commerce.queue import CandidateQueue
from src.commerce.schemas import (
    AgentRole,
    CandidateStatus,
    CommerceCriticRecommendation,
    DraftReviewStatus,
    HumanDecisionRecord,
    HumanDecisionType,
    PipelineGateStatus,
    ProductLane,
    RealizedOutcomeRecord,
    ReturnPostagePayer,
    ReturnRoute,
    SupplierBackedProduct,
    SupplierPolicyRules,
)
from src.commerce.three_agent_pipeline import ThreeAgentPipeline


@pytest.fixture
def pet_pass_product():
    return SupplierBackedProduct(
        supplier_name="Go Dropship",
        supplier_sku="PET-73110",
        product_name="2-in-1 pet feeder",
        supplier_cost=8.64,
        lane=ProductLane.EVERGREEN,
        market_price=16.99,
        platform_fees=3.18,
        return_allowance=1.25,
        market_price_validated=True,
        platform_fees_validated=True,
        return_allowance_validated=True,
        expected_profit=3.92,
        expected_margin=0.2307,
    )


@pytest.fixture
def pet_reject_product():
    return SupplierBackedProduct(
        supplier_name="Go Dropship",
        supplier_sku="PET-73135",
        product_name="anti-splash cat litter box",
        supplier_cost=12.68,
        lane=ProductLane.EVERGREEN,
        market_price=16.99,
        platform_fees=3.18,
        return_allowance=1.50,
        market_price_validated=True,
        platform_fees_validated=True,
        return_allowance_validated=True,
        expected_profit=-0.37,
        expected_margin=-0.0218,
    )


@pytest.fixture
def go_dropship_rules():
    return SupplierPolicyRules(
        supplier_id="go_dropship",
        dispatch_time_days=2,
        shipping_services=["TRACKED_2_BUSINESS_DAY"],
        remote_surcharge=0.0,
        blind_ship=True,
        return_route=ReturnRoute.SUPPLIER,
        rma_required=True,
        return_postage=ReturnPostagePayer.BUYER,
        supplier_fault_resolution="REFUND_OR_REPLACE_AFTER_EVIDENCE",
    )


def test_profitable_pass_product(tmp_path, pet_pass_product, go_dropship_rules):
    db_path = str(tmp_path / "commerce.db")
    db = CommerceDatabase(db_path)
    db.save_supplier_policy_rules(go_dropship_rules)

    pipeline = ThreeAgentPipeline(db=db)
    result = pipeline.run(
        product=pet_pass_product,
        target_price=16.99,
        platform_fee=3.18,
        return_allowance=1.25,
        rules=go_dropship_rules,
    )

    # 1. Scout
    assert result.scout_eval.recommendation == "PROCEED"
    assert result.scout_eval.score >= 75

    # 2. Commercial
    assert result.commercial_eval.meets_minimum_margin is True
    assert result.commercial_eval.expected_profit == 3.92
    assert result.commercial_eval.expected_margin == 0.2307
    assert result.commercial_eval.supplier_valid is True
    assert result.commercial_eval.policy_compatible is True

    # 3. Critic & Safety Gate
    assert result.gate_status in (PipelineGateStatus.READY_FOR_HUMAN_REVIEW, PipelineGateStatus.REVIEW)
    assert result.queue_status == CandidateStatus.REVIEW
    assert result.auto_approved is False
    assert result.published is False
    assert result.human_approval_required is True

    # Candidate in queue is awaiting human review
    candidate = pipeline.queue.get_candidate(result.candidate_id)
    assert candidate is not None
    assert candidate.status == CandidateStatus.REVIEW


def test_low_margin_reject(tmp_path, pet_reject_product, go_dropship_rules):
    db_path = str(tmp_path / "commerce.db")
    db = CommerceDatabase(db_path)
    db.save_supplier_policy_rules(go_dropship_rules)

    pipeline = ThreeAgentPipeline(db=db)
    result = pipeline.run(
        product=pet_reject_product,
        target_price=16.99,
        platform_fee=3.18,
        return_allowance=1.50,
        rules=go_dropship_rules,
    )

    # Commercial rejects
    assert result.commercial_eval.meets_minimum_margin is False
    assert result.commercial_eval.expected_profit == -0.37
    assert result.commercial_eval.expected_margin < DEFAULT_MIN_MARGIN_PCT

    # Critic blocks
    assert result.critic_eval.recommendation == CommerceCriticRecommendation.BLOCK

    # Deterministic Gate rejects
    assert result.gate_status == PipelineGateStatus.REJECT
    assert result.queue_status == CandidateStatus.REJECTED

    # Candidate in queue marked REJECTED
    candidate = pipeline.queue.get_candidate(result.candidate_id)
    assert candidate is not None
    assert candidate.status == CandidateStatus.REJECTED
    assert "below the mandatory 20.00% minimum" in candidate.rejection_reason


def test_critic_caution_for_thin_margin(tmp_path, go_dropship_rules):
    db_path = str(tmp_path / "commerce.db")
    db = CommerceDatabase(db_path)
    db.save_supplier_policy_rules(go_dropship_rules)

    # Product with 20.5% margin (meets 20% floor, but thin cushion < 22%)
    product = SupplierBackedProduct(
        supplier_name="Go Dropship",
        supplier_sku="PET-THIN-01",
        product_name="standard pet bowl",
        supplier_cost=7.00,
        lane=ProductLane.EVERGREEN,
    )

    pipeline = ThreeAgentPipeline(db=db)
    # Price £10.00, Cost £7.00, Fee £0.70, Return £0.25 -> Cost £7.95, Profit £2.05, Margin 20.5%
    result = pipeline.run(
        product=product,
        target_price=10.00,
        platform_fee=0.70,
        return_allowance=0.25,
        rules=go_dropship_rules,
    )

    assert result.commercial_eval.meets_minimum_margin is True
    assert 0.20 <= result.commercial_eval.expected_margin < 0.22
    assert result.critic_eval.recommendation == CommerceCriticRecommendation.BLOCK
    assert any("THIN_CUSHION" in flag for flag in result.critic_eval.risk_flags)
    assert any("PRICE_SENSITIVITY" in flag for flag in result.critic_eval.risk_flags)
    assert any("SHIPPING_SHOCK" in flag for flag in result.critic_eval.risk_flags)
    assert result.critic_eval.risk_score >= 80
    assert result.gate_status == PipelineGateStatus.REJECT
    assert result.queue_status == CandidateStatus.REJECTED


def test_christmas_in_january_targets_next_season(tmp_path):
    db_path = str(tmp_path / "commerce.db")
    db = CommerceDatabase(db_path)

    seasonal_product = SupplierBackedProduct(
        supplier_name="Go Dropship",
        supplier_sku="HOM-55216",
        product_name="6pc Christmas feather ornaments",
        supplier_cost=3.94,
        lane=ProductLane.SEASONAL,
    )

    pipeline = ThreeAgentPipeline(db=db)

    result = pipeline.run(
        product=seasonal_product,
        target_price=10.00,
        platform_fee=1.50,
        return_allowance=0.50,
        as_of=date(2026, 1, 15),
    )

    assert result.scout_eval.seasonal_event == "Christmas"
    assert result.scout_eval.seasonal_window_status == "UPCOMING"
    assert result.critic_eval.recommendation == CommerceCriticRecommendation.CAUTION
    assert result.gate_status == PipelineGateStatus.REVIEW
    assert result.queue_status == CandidateStatus.REVIEW


def test_critic_block_non_blind_shipping(tmp_path, pet_pass_product):
    db_path = str(tmp_path / "commerce.db")
    db = CommerceDatabase(db_path)

    # Supplier policy that forbids blind shipping
    bad_rules = SupplierPolicyRules(
        supplier_id="non_blind_supplier",
        dispatch_time_days=2,
        shipping_services=["STANDARD"],
        remote_surcharge=0.0,
        blind_ship=False,
        return_route=ReturnRoute.SUPPLIER,
        rma_required=False,
        return_postage=ReturnPostagePayer.SELLER,
    )

    pipeline = ThreeAgentPipeline(db=db)
    result = pipeline.run(
        product=pet_pass_product,
        target_price=16.99,
        platform_fee=3.18,
        return_allowance=1.25,
        rules=bad_rules,
    )

    assert result.commercial_eval.policy_compatible is False
    assert result.critic_eval.recommendation == CommerceCriticRecommendation.BLOCK
    assert any("POLICY_BLOCK" in flag for flag in result.critic_eval.risk_flags)
    assert result.gate_status == PipelineGateStatus.REJECT


def test_history_persistence(tmp_path, pet_pass_product, go_dropship_rules):
    db_path = str(tmp_path / "commerce.db")
    db = CommerceDatabase(db_path)
    db.save_supplier_policy_rules(go_dropship_rules)

    pipeline = ThreeAgentPipeline(db=db)
    result = pipeline.run(
        product=pet_pass_product,
        target_price=16.99,
        platform_fee=3.18,
        return_allowance=1.25,
        rules=go_dropship_rules,
        persist_history=True,
    )

    # Verify agent_evaluations
    evals = db.list_agent_evaluations(pipeline_run_id=result.pipeline_run_id)
    assert len(evals) == 3
    roles = {e.agent_role for e in evals}
    assert roles == {AgentRole.SCOUT, AgentRole.COMMERCIAL, AgentRole.CRITIC}
    for e in evals:
        assert e.supplier_sku == pet_pass_product.supplier_sku
        assert e.pipeline_run_id == result.pipeline_run_id
        assert e.created_at is not None

    # Test human_decisions persistence
    decision_record = HumanDecisionRecord(
        candidate_id=result.candidate_id,
        supplier_sku=pet_pass_product.supplier_sku,
        pipeline_run_id=result.pipeline_run_id,
        decision=HumanDecisionType.APPROVED,
        reviewer_id="reviewer_sarah",
        reason_category="GOOD_OPPORTUNITY",
        notes="High demand product with solid 23% margin.",
    )
    saved_dec = db.record_human_decision(decision_record)
    loaded_decs = db.list_human_decisions(candidate_id=result.candidate_id)
    assert len(loaded_decs) == 1
    assert loaded_decs[0].reviewer_id == "reviewer_sarah"
    assert loaded_decs[0].decision == HumanDecisionType.APPROVED

    # Test realized_outcomes persistence
    outcome_record = RealizedOutcomeRecord(
        supplier_sku=pet_pass_product.supplier_sku,
        supplier_name=pet_pass_product.supplier_name,
        listing_id="EBAY-PET-73110",
        units_sold=12,
        actual_sale_price=16.99,
        actual_supplier_cost=8.64,
        actual_platform_fees=3.18,
        realized_net_profit=47.04,
        realized_margin_pct=0.2307,
        return_count=0,
        return_reasons=[],
    )
    saved_outcome = db.save_realized_outcome(outcome_record)
    loaded_outcome = db.get_realized_outcome(pet_pass_product.supplier_sku, pet_pass_product.supplier_name)
    assert loaded_outcome is not None
    assert loaded_outcome.units_sold == 12
    assert loaded_outcome.realized_net_profit == 47.04


def test_human_gate_and_no_auto_publish(tmp_path, pet_pass_product, go_dropship_rules):
    db_path = str(tmp_path / "commerce.db")
    db = CommerceDatabase(db_path)
    db.save_supplier_policy_rules(go_dropship_rules)

    pipeline = ThreeAgentPipeline(db=db)
    result = pipeline.run(
        product=pet_pass_product,
        target_price=16.99,
        platform_fee=3.18,
        return_allowance=1.25,
        rules=go_dropship_rules,
    )

    # 1. Candidate is in REVIEW (NOT approved for listing)
    candidate = pipeline.queue.get_candidate(result.candidate_id)
    assert candidate.status == CandidateStatus.REVIEW

    # 2. Cannot create an eBay listing draft while in REVIEW stage
    with pytest.raises(ValueError, match="APPROVED_FOR_LISTING"):
        pipeline.queue.create_ebay_draft(candidate.candidate_id)

    # 3. Explicit human approval is mandatory to advance to APPROVED_FOR_LISTING
    approved_candidate = pipeline.queue.approve_for_listing(
        candidate.candidate_id,
        reviewer="human_reviewer_42",
        notes="Reviewed and confirmed pricing.",
    )
    assert approved_candidate.status == CandidateStatus.APPROVED_FOR_LISTING

    # 4. Now eBay listing draft can be created
    draft = pipeline.queue.create_ebay_draft(candidate.candidate_id)
    assert draft.status == DraftReviewStatus.DRAFT_CREATED
    assert draft.human_approval_required is True

    # 5. Cannot publish draft without human approval
    ebay_adapter = EBayAdapter()
    listing = ebay_adapter.create_listing(draft)
    assert listing.human_approved is False

    with pytest.raises(PermissionError, match="Human approval is required"):
        ebay_adapter.publish_listing(listing)

    # 6. Advance draft through human review lifecycle
    pipeline.queue.submit_draft_for_review(draft.draft_id)
    approved_draft = pipeline.queue.approve_draft_to_publish(
        draft.draft_id,
        reviewer="senior_merchant_lead",
    )
    assert approved_draft.status == DraftReviewStatus.APPROVED_TO_PUBLISH

    approved_listing = ebay_adapter.create_listing(approved_draft)
    assert approved_listing.human_approved is True
    pub_res = ebay_adapter.publish_listing(approved_listing)
    assert pub_res["status"] == "ACTIVE"


def test_learning_history_cannot_alter_20pct_threshold(tmp_path, go_dropship_rules):
    db_path = str(tmp_path / "commerce.db")
    db = CommerceDatabase(db_path)
    db.save_supplier_policy_rules(go_dropship_rules)

    # Seed excellent learning history (100 units sold, 0 returns, huge profit)
    db.save_realized_outcome(
        RealizedOutcomeRecord(
            supplier_sku="PET-BORDERLINE",
            supplier_name="Go Dropship",
            units_sold=100,
            return_count=0,
            realized_net_profit=500.0,
            realized_margin_pct=0.30,
        )
    )

    # Product configured to yield 19.5% margin (0.5% below 20.00% floor)
    # Sale £20.00, Cost £12.00, Fee £3.00, Return £1.10 -> Total Cost £16.10, Net Profit £3.90 -> Margin 19.50%
    borderline_product = SupplierBackedProduct(
        supplier_name="Go Dropship",
        supplier_sku="PET-BORDERLINE",
        product_name="borderline margin pet feeder",
        supplier_cost=12.00,
        lane=ProductLane.EVERGREEN,
    )

    pipeline = ThreeAgentPipeline(db=db)
    result = pipeline.run(
        product=borderline_product,
        target_price=20.00,
        platform_fee=3.00,
        return_allowance=1.10,
        rules=go_dropship_rules,
    )

    # Even with pristine history, the deterministic 20% margin rule is absolute
    assert result.commercial_eval.meets_minimum_margin is False
    assert result.commercial_eval.expected_margin == 0.1950
    assert result.gate_status == PipelineGateStatus.REJECT
    assert result.queue_status == CandidateStatus.REJECTED
    assert "below the mandatory 20.00% minimum" in result.reasons[0]
