"""Three-agent commerce evaluation pipeline.

Coordinates:
  Market / Supplier Evidence
  → Agent 1: Product Scout
  → Agent 2: Commercial / Seller
  → Agent 3: Critic / Risk
  → Deterministic Safety Gates (20% margin floor, anti-retail sourcing, policy match)
  → REJECT / REVIEW / READY_FOR_HUMAN_REVIEW
  → Mandatory Human Decision

Guards:
  - Agents NEVER approve listings.
  - Agents NEVER publish to eBay.
  - Agents NEVER order from suppliers.
  - Agents NEVER modify the 20% minimum margin rule.
  - auto_approved is hard-coded to False.
  - published is hard-coded to False.
  - Human approval remains mandatory.
"""

from datetime import date, datetime, timezone
from typing import Any, Optional
import uuid

from src.commerce.agents.critic import CommerceCriticAgent
from src.commerce.agents.product_scout import ProductScoutAgent
from src.commerce.agents.seller_a import CommercialAgent
from src.commerce.database import CommerceDatabase
from src.commerce.profit_engine import DEFAULT_MIN_MARGIN_PCT
from src.commerce.queue import CandidateQueue
from src.commerce.schemas import (
    AgentEvaluationRecord,
    AgentRole,
    CandidateStatus,
    CommercialEvaluationResult,
    CommerceCriticRecommendation,
    CriticEvaluationResult,
    PipelineGateStatus,
    PipelineRunResult,
    Platform,
    ProductCandidate,
    ProductLane,
    ScoutEvaluationResult,
    SupplierBackedProduct,
    SupplierPolicyRules,
    SupplierProfitStatus,
)


class ThreeAgentPipeline:
    """End-to-end multi-agent evaluation pipeline with strict safety gates."""

    def __init__(
        self,
        db: Optional[CommerceDatabase] = None,
        db_path: str = "data/commerce.db",
    ):
        self.db = db if db is not None else CommerceDatabase(db_path=db_path)
        self.queue = CandidateQueue(db=self.db)
        self.scout = ProductScoutAgent(db=self.db)
        self.commercial = CommercialAgent(db=self.db)
        self.critic = CommerceCriticAgent(db=self.db)

    def run(
        self,
        product: Any,
        target_price: Optional[float] = None,
        platform_fee: Optional[float] = None,
        return_allowance: Optional[float] = None,
        shipping: Optional[float] = None,
        rules: Optional[SupplierPolicyRules] = None,
        as_of: Optional[date] = None,
        persist_history: bool = True,
    ) -> PipelineRunResult:
        run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"

        # 1. Resolve product identity
        if isinstance(product, SupplierBackedProduct):
            sku = product.supplier_sku
            supplier_name = product.supplier_name
            title = product.product_name
            cost = product.supplier_cost
            lane = product.lane
            price = target_price if target_price is not None else product.market_price
            fee = platform_fee if platform_fee is not None else (product.platform_fees or 0.0)
            returns = return_allowance if return_allowance is not None else (product.return_allowance or 0.0)
        elif isinstance(product, ProductCandidate):
            sku = product.sku
            supplier_name = product.supplier_id
            title = product.title
            cost = product.supplier_cost
            lane = ProductLane.EVERGREEN
            price = target_price if target_price is not None else product.target_price
            fee = platform_fee if platform_fee is not None else product.estimated_fee
            returns = return_allowance if return_allowance is not None else 0.0
        elif isinstance(product, dict):
            sku = product.get("supplier_sku") or product.get("sku", "UNKNOWN")
            supplier_name = product.get("supplier_name") or product.get("supplier_id", "Go Dropship")
            title = product.get("product_name") or product.get("title", "Unknown Product")
            cost = float(product.get("supplier_cost") or product.get("cost", 0.0))
            lane = product.get("lane", ProductLane.EVERGREEN)
            price = target_price if target_price is not None else product.get("market_price") or product.get("target_price")
            fee = platform_fee if platform_fee is not None else product.get("platform_fees") or product.get("estimated_fee", 0.0)
            returns = return_allowance if return_allowance is not None else product.get("return_allowance", 0.0)
        else:
            sku = getattr(product, "supplier_sku", getattr(product, "sku", "UNKNOWN"))
            supplier_name = getattr(product, "supplier_name", getattr(product, "supplier_id", "Go Dropship"))
            title = getattr(product, "product_name", getattr(product, "title", "Unknown Product"))
            cost = float(getattr(product, "supplier_cost", getattr(product, "cost", 0.0)))
            lane = getattr(product, "lane", ProductLane.EVERGREEN)
            price = target_price if target_price is not None else getattr(product, "market_price", getattr(product, "target_price", None))
            fee = platform_fee if platform_fee is not None else getattr(product, "platform_fees", getattr(product, "estimated_fee", 0.0))
            returns = return_allowance if return_allowance is not None else getattr(product, "return_allowance", 0.0)

        candidate_id = f"CAND-EBAY-{sku}"

        # Resolve supplier rules if not supplied
        if rules is None and supplier_name:
            norm_id = supplier_name.lower().replace(" ", "_")
            rules = self.db.get_supplier_policy_rules(norm_id)

        # -------------------------------------------------------------
        # Step 1: Agent 1 - Product Scout
        # -------------------------------------------------------------
        scout_eval: ScoutEvaluationResult = self.scout.evaluate(
            product=product,
            as_of=as_of,
        )
        if persist_history:
            self.db.save_agent_evaluation(
                AgentEvaluationRecord(
                    pipeline_run_id=run_id,
                    supplier_sku=sku,
                    supplier_name=supplier_name,
                    agent_role=AgentRole.SCOUT,
                    recommendation=scout_eval.recommendation,
                    score=float(scout_eval.score),
                    confidence=scout_eval.confidence,
                    evidence_snapshot={
                        "product_name": title,
                        "lane": scout_eval.lane.value if hasattr(scout_eval.lane, "value") else str(scout_eval.lane),
                        "seasonal_event": scout_eval.seasonal_event,
                        "seasonal_window_status": scout_eval.seasonal_window_status,
                        "competition_density": scout_eval.competition_density,
                    },
                    evaluation_details={"reasons": scout_eval.reasons},
                )
            )

        # -------------------------------------------------------------
        # Step 2: Agent 2 - Commercial / Seller
        # -------------------------------------------------------------
        commercial_eval: CommercialEvaluationResult = self.commercial.evaluate(
            product=product,
            target_price=price,
            shipping=shipping,
            platform_fee=fee,
            return_allowance=returns,
            rules=rules,
        )
        if persist_history:
            self.db.save_agent_evaluation(
                AgentEvaluationRecord(
                    pipeline_run_id=run_id,
                    supplier_sku=sku,
                    supplier_name=supplier_name,
                    agent_role=AgentRole.COMMERCIAL,
                    recommendation=commercial_eval.recommendation,
                    score=commercial_eval.expected_margin * 100.0,
                    confidence=0.90 if commercial_eval.proposed_price > 0 else 0.40,
                    evidence_snapshot={
                        "proposed_price": commercial_eval.proposed_price,
                        "supplier_cost": commercial_eval.supplier_cost,
                        "shipping": commercial_eval.shipping,
                        "platform_fee": commercial_eval.platform_fee,
                        "return_buffer": commercial_eval.return_buffer,
                    },
                    evaluation_details={
                        "expected_profit": commercial_eval.expected_profit,
                        "expected_margin": commercial_eval.expected_margin,
                        "meets_minimum_margin": commercial_eval.meets_minimum_margin,
                        "supplier_valid": commercial_eval.supplier_valid,
                        "policy_compatible": commercial_eval.policy_compatible,
                        "reasons": commercial_eval.reasons,
                    },
                )
            )

        # -------------------------------------------------------------
        # Step 3: Agent 3 - Critic / Risk
        # -------------------------------------------------------------
        critic_eval: CriticEvaluationResult = self.critic.evaluate(
            product=product,
            commercial_eval=commercial_eval,
            scout_eval=scout_eval,
            rules=rules,
            as_of=as_of,
        )
        if persist_history:
            self.db.save_agent_evaluation(
                AgentEvaluationRecord(
                    pipeline_run_id=run_id,
                    supplier_sku=sku,
                    supplier_name=supplier_name,
                    agent_role=AgentRole.CRITIC,
                    recommendation=critic_eval.recommendation.value,
                    score=100.0 - float(critic_eval.risk_score),
                    confidence=0.85,
                    evidence_snapshot={
                        "risk_score": critic_eval.risk_score,
                        "margin_cushion": critic_eval.margin_cushion,
                        "stress_test_results": critic_eval.stress_test_results,
                    },
                    evaluation_details={
                        "risk_flags": critic_eval.risk_flags,
                        "reasoning": critic_eval.reasoning,
                    },
                )
            )

        # -------------------------------------------------------------
        # Step 4: Deterministic Safety Gates (HARD CODED - NO AGENT OVERRIDE)
        # -------------------------------------------------------------
        gate_reasons: list[str] = []
        gate_status: PipelineGateStatus
        queue_status: CandidateStatus

        # Gate 1: 20% Margin Safety Rule (Immutable)
        if not commercial_eval.meets_minimum_margin or commercial_eval.expected_margin < DEFAULT_MIN_MARGIN_PCT:
            gate_status = PipelineGateStatus.REJECT
            queue_status = CandidateStatus.REJECTED
            gate_reasons.append(
                f"Deterministic margin gate failed: margin {commercial_eval.expected_margin:.2%} "
                f"is below the mandatory 20.00% minimum (profit: £{commercial_eval.expected_profit:.2f})."
            )
        # Gate 2: Sourcing Validity (Anti-retail dropshipping)
        elif not commercial_eval.supplier_valid:
            gate_status = PipelineGateStatus.REJECT
            queue_status = CandidateStatus.REJECTED
            gate_reasons.append(
                f"Deterministic sourcing gate failed: {commercial_eval.reasons[0]}"
            )
        # Gate 3: Critic Hard Block
        elif critic_eval.recommendation == CommerceCriticRecommendation.BLOCK:
            gate_status = PipelineGateStatus.REJECT
            queue_status = CandidateStatus.REJECTED
            gate_reasons.append(
                f"Critic risk gate blocked: {critic_eval.reasoning}"
            )
        # Gate 4: Caution / Near Threshold Review
        elif (
            critic_eval.recommendation == CommerceCriticRecommendation.CAUTION
            or commercial_eval.expected_margin < 0.22
            or not commercial_eval.policy_compatible
        ):
            gate_status = PipelineGateStatus.REVIEW
            queue_status = CandidateStatus.REVIEW
            caution_factors = critic_eval.risk_flags or ["Thin margin cushion (<22%)"]
            gate_reasons.append(
                f"Promoted to REVIEW with caution: {'; '.join(caution_factors)}."
            )
        # Gate 5: Clean Pass
        else:
            gate_status = PipelineGateStatus.READY_FOR_HUMAN_REVIEW
            queue_status = CandidateStatus.REVIEW
            gate_reasons.append(
                "Passed all 3 agent evaluations and deterministic safety gates. "
                "Ready for mandatory human listing decision."
            )

        # -------------------------------------------------------------
        # Step 5: Candidate Queue Synchronization
        # -------------------------------------------------------------
        # Look up existing candidate or create
        existing = self.queue.get_candidate(candidate_id)
        supplier_profit_status = (
            SupplierProfitStatus.VERIFIED_PROFITABLE
            if commercial_eval.meets_minimum_margin and commercial_eval.supplier_valid
            else (
                SupplierProfitStatus.VERIFIED_LOW_MARGIN
                if commercial_eval.supplier_valid
                else SupplierProfitStatus.SUPPLIER_REJECTED
            )
        )

        if existing is None:
            candidate = self.queue.enqueue(
                ProductCandidate(
                    candidate_id=candidate_id,
                    sku=sku,
                    title=title,
                    category=commercial_eval.category,
                    supplier_id=supplier_name,
                    target_platform=Platform.EBAY,
                    supplier_cost=commercial_eval.supplier_cost,
                    target_price=commercial_eval.proposed_price,
                    shipping_cost=commercial_eval.shipping,
                    estimated_fee=commercial_eval.platform_fee,
                    estimated_profit=commercial_eval.expected_profit,
                    estimated_margin_pct=commercial_eval.expected_margin,
                    supplier_profit_status=supplier_profit_status,
                    status=CandidateStatus.NEW,
                    notes=gate_reasons[-1],
                )
            )
        else:
            candidate = existing

        # Advance queue state according to gate
        if queue_status == CandidateStatus.REJECTED:
            self.queue.reject(candidate_id, reason=gate_reasons[-1])
        else:
            if candidate.status == CandidateStatus.NEW:
                candidate = self.queue.transition(candidate_id, CandidateStatus.VERIFIED)
            if candidate.status == CandidateStatus.VERIFIED:
                candidate = self.queue.submit_for_review(candidate_id, notes=gate_reasons[-1])

        return PipelineRunResult(
            pipeline_run_id=run_id,
            supplier_sku=sku,
            supplier_name=supplier_name,
            candidate_id=candidate_id,
            gate_status=gate_status,
            queue_status=queue_status,
            auto_approved=False,
            published=False,
            human_approval_required=True,
            scout_eval=scout_eval,
            commercial_eval=commercial_eval,
            critic_eval=critic_eval,
            reasons=gate_reasons,
        )

    def run_for_sku(
        self,
        supplier_sku: str,
        supplier_name: str = "Go Dropship",
        as_of: Optional[date] = None,
        persist_history: bool = True,
    ) -> PipelineRunResult:
        """Run pipeline for a staged supplier-backed product in the database."""
        product = self.db.get_supplier_backed_product(supplier_name, supplier_sku)
        if product is None:
            raise KeyError(f"Product '{supplier_name}/{supplier_sku}' not found in staged database.")

        return self.run(
            product=product,
            target_price=product.market_price,
            platform_fee=product.platform_fees,
            return_allowance=product.return_allowance,
            as_of=as_of,
            persist_history=persist_history,
        )

    @staticmethod
    def market_evidence_ready(product: SupplierBackedProduct) -> bool:
        """Return True only when a staged product has a usable validated market price."""
        return product.market_price is not None and product.market_price > 0

    def run_staged_batch(
        self,
        as_of: Optional[date] = None,
        persist_history: bool = True,
    ) -> list[PipelineRunResult]:
        """Run pipeline over staged products that have usable market evidence."""
        products = self.db.list_supplier_backed_products()
        results: list[PipelineRunResult] = []

        for product in products:
            if not self.market_evidence_ready(product):
                continue

            results.append(
                self.run(
                    product=product,
                    target_price=product.market_price,
                    platform_fee=product.platform_fees,
                    return_allowance=product.return_allowance,
                    as_of=as_of,
                    persist_history=persist_history,
                )
            )

        return results
