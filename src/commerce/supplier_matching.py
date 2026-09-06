from typing import Optional, Protocol

from pydantic import BaseModel, Field

from src.commerce.opportunity_scoring import OpportunityDecision, ScoredMarketOpportunity
from src.commerce.profit_engine import DEFAULT_MIN_MARGIN_PCT, calculate_profit
from src.commerce.schemas import (
    CandidateStatus,
    Platform,
    ProductCandidate,
    ProfitDecision,
    SupplierProduct,
    SupplierProfitStatus,
    SupplierType,
    SupplierValidationResult,
    SupplierVerificationStatus,
)
from src.commerce.supplier_validator import validate_supplier


class ManualSupplierInput(BaseModel):
    """Supplier facts entered by a human; this object performs no live lookup."""

    name: Optional[str] = Field(default=None, min_length=1)
    sku: Optional[str] = Field(default=None, min_length=1)
    cost: Optional[float] = Field(default=None, gt=0)
    shipping: Optional[float] = Field(default=None, ge=0)
    stock: Optional[int] = Field(default=None, ge=0)
    direct_ship: Optional[bool] = None
    verification_status: SupplierVerificationStatus = SupplierVerificationStatus.PENDING


class SupplierMatchResult(BaseModel):
    status: SupplierProfitStatus
    candidate: Optional[ProductCandidate] = None
    supplier_validation: Optional[SupplierValidationResult] = None
    profit_decision: Optional[ProfitDecision] = None
    reason: str


class SupplierMatchInterface(Protocol):
    def verify(
        self,
        opportunity: ScoredMarketOpportunity,
        supplier: ManualSupplierInput,
        *,
        platform_fee: float = 0.0,
        return_buffer: float = 0.0,
        min_margin_pct: float = DEFAULT_MIN_MARGIN_PCT,
    ) -> SupplierMatchResult: ...


class ManualSupplierMatcher:
    """Connects an eBay shortlist item to manually verified supplier economics."""

    def verify(
        self,
        opportunity: ScoredMarketOpportunity,
        supplier: ManualSupplierInput,
        *,
        platform_fee: float = 0.0,
        return_buffer: float = 0.0,
        min_margin_pct: float = DEFAULT_MIN_MARGIN_PCT,
    ) -> SupplierMatchResult:
        if opportunity.decision is not OpportunityDecision.SHORTLIST:
            raise ValueError("Only SHORTLIST eBay opportunities can enter supplier matching.")

        listing = opportunity.listing
        if supplier.verification_status is SupplierVerificationStatus.REJECTED:
            return SupplierMatchResult(
                status=SupplierProfitStatus.SUPPLIER_REJECTED,
                reason="Manual supplier verification rejected this match.",
            )

        required = (supplier.name, supplier.sku, supplier.cost, supplier.shipping,
                    supplier.stock, supplier.direct_ship)
        if (supplier.verification_status is not SupplierVerificationStatus.VERIFIED
                or any(value is None for value in required)):
            return SupplierMatchResult(
                status=SupplierProfitStatus.NEEDS_SUPPLIER_DATA,
                reason="Complete all supplier fields and mark verification status VERIFIED.",
            )

        candidate = ProductCandidate(
            candidate_id=f"CAND-EBAY-{listing.item_id}",
            sku=supplier.sku,
            title=listing.title,
            category=listing.category,
            supplier_id=supplier.name,
            target_platform=Platform.EBAY,
            supplier_cost=supplier.cost,
            target_price=float(listing.price),
            shipping_cost=supplier.shipping,
            estimated_fee=platform_fee,
            status=CandidateStatus.NEW,
        )

        product = SupplierProduct(
            supplier_id=supplier.name,
            supplier_name=supplier.name,
            sku=supplier.sku,
            title=listing.title,
            supplier_type=SupplierType.DIRECT if supplier.direct_ship else SupplierType.WHOLESALE,
            cost=supplier.cost,
            shipping_cost=supplier.shipping,
            inventory_count=supplier.stock,
            allows_reselling=True,
        )
        validation = validate_supplier(product)
        if not validation.is_valid:
            return self._result(
                candidate, SupplierProfitStatus.SUPPLIER_REJECTED,
                validation.reason, validation=validation,
            )

        profit = calculate_profit(
            supplier_cost=supplier.cost,
            shipping=supplier.shipping,
            platform_fee=platform_fee,
            return_buffer=return_buffer,
            sale_price=float(listing.price),
            min_margin_pct=min_margin_pct,
        )
        status = (
            SupplierProfitStatus.VERIFIED_PROFITABLE
            if profit.allowed else SupplierProfitStatus.VERIFIED_LOW_MARGIN
        )
        candidate.sku = supplier.sku
        candidate.supplier_id = supplier.name
        candidate.supplier_cost = supplier.cost
        candidate.shipping_cost = supplier.shipping
        candidate.estimated_profit = profit.net_profit
        candidate.estimated_margin_pct = profit.margin_pct
        candidate.supplier_profit_status = status
        if status is SupplierProfitStatus.VERIFIED_PROFITABLE:
            candidate.status = CandidateStatus.VERIFIED
        return SupplierMatchResult(
            status=status,
            candidate=candidate,
            supplier_validation=validation,
            profit_decision=profit,
            reason=profit.reason,
        )

    @staticmethod
    def _result(candidate, status, reason, validation=None):
        candidate.supplier_profit_status = status
        return SupplierMatchResult(
            status=status,
            candidate=candidate,
            supplier_validation=validation,
            reason=reason,
        )


def verify_manual_supplier_match(
    opportunity: ScoredMarketOpportunity,
    supplier: ManualSupplierInput,
    **profit_inputs,
) -> SupplierMatchResult:
    return ManualSupplierMatcher().verify(opportunity, supplier, **profit_inputs)
