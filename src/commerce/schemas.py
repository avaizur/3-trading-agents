from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Platform(str, Enum):
    EBAY = "EBAY"
    AMAZON = "AMAZON"


class PlatformStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    ON_HOLD = "ON_HOLD"


class SupplierType(str, Enum):
    WHOLESALE = "WHOLESALE"
    DISTRIBUTOR = "DISTRIBUTOR"
    MANUFACTURER = "MANUFACTURER"
    DIRECT = "DIRECT"
    RETAIL = "RETAIL"  # Prohibited for dropshipping / arbitrage


class ListingApprovalStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ListingStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class SupplierOrderStatus(str, Enum):
    MANUAL_PENDING = "MANUAL_PENDING"
    MANUAL_ORDERED = "MANUAL_ORDERED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class CommerceCriticRecommendation(str, Enum):
    CONTINUE = "CONTINUE"
    CAUTION = "CAUTION"
    BLOCK = "BLOCK"


class CandidateStatus(str, Enum):
    NEW = "NEW"
    VERIFIED = "VERIFIED"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"
    APPROVED_FOR_LISTING = "APPROVED_FOR_LISTING"


class SupplierVerificationStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class SupplierProfitStatus(str, Enum):
    VERIFIED_PROFITABLE = "VERIFIED_PROFITABLE"
    VERIFIED_LOW_MARGIN = "VERIFIED_LOW_MARGIN"
    SUPPLIER_REJECTED = "SUPPLIER_REJECTED"
    NEEDS_SUPPLIER_DATA = "NEEDS_SUPPLIER_DATA"


ProductQueueStatus = CandidateStatus


class DraftReviewStatus(str, Enum):
    DRAFT_CREATED = "DRAFT_CREATED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED_TO_PUBLISH = "APPROVED_TO_PUBLISH"
    REJECTED = "REJECTED"


HumanReviewStatus = DraftReviewStatus
ListingDraftStatus = DraftReviewStatus


class SupplierProduct(BaseModel):
    supplier_id: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    title: str = Field(min_length=1)
    supplier_type: SupplierType
    cost: float = Field(gt=0)
    shipping_cost: float = Field(default=0.0, ge=0)
    inventory_count: Optional[int] = Field(default=None, ge=0)
    lead_time_days: Optional[int] = Field(default=None, ge=0)
    allows_reselling: bool = True
    supplier_name: Optional[str] = None
    supplier_url: Optional[str] = None


class SupplierValidationResult(BaseModel):
    is_valid: bool
    reason: str
    supplier_type: SupplierType
    retail_dropshipping_blocked: bool = False
    passed_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProfitCalculationInput(BaseModel):
    supplier_cost: float = Field(gt=0, description="Cost of goods from supplier")
    shipping: float = Field(ge=0, default=0.0, description="Shipping and fulfillment cost")
    platform_fee: float = Field(ge=0, default=0.0, description="Platform listing/final value fees")
    return_buffer: float = Field(ge=0, default=0.0, description="Allowance for returns and damages")
    sale_price: float = Field(gt=0, description="Target listing sale price")
    min_margin_pct: float = Field(
        default=0.20,
        ge=0.0,
        description="Minimum acceptable net margin ratio (default 20% or 0.20)",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_min_margin(cls, data):
        if isinstance(data, dict) and "min_margin_pct" in data:
            val = data["min_margin_pct"]
            if val is not None and val > 1.0:
                data["min_margin_pct"] = val / 100.0
        return data


class ProfitDecision(BaseModel):
    allowed: bool
    reason: str
    supplier_cost: float
    shipping: float
    platform_fee: float
    return_buffer: float
    total_cost: float
    sale_price: float
    net_profit: float
    margin_pct: float
    min_margin_pct: float
    meets_minimum_margin: bool


class ProductScoutOpportunity(BaseModel):
    opportunity_id: str = Field(min_length=1)
    supplier_id: str = Field(min_length=1)
    supplier_sku: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    target_platform: Platform = Platform.EBAY
    supplier_cost: float = Field(gt=0)
    estimated_shipping: float = Field(ge=0, default=0.0)
    estimated_platform_fee: float = Field(ge=0, default=0.0)
    estimated_return_buffer: float = Field(ge=0, default=0.0)
    suggested_sale_price: float = Field(gt=0)
    estimated_net_profit: float
    estimated_margin_pct: float
    scouted_at: datetime
    confidence: float = Field(ge=0, le=1)


class SellerListingDraft(BaseModel):
    agent_name: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    target_platform: Platform = Platform.EBAY
    proposed_price: float = Field(gt=0)
    strategy_notes: str = ""
    human_approval_required: bool = True
    approval_status: ListingApprovalStatus = ListingApprovalStatus.PENDING_APPROVAL
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_approval_constraint(self):
        if not self.human_approval_required:
            raise ValueError("human_approval_required cannot be False (policy requirement)")
        if self.approval_status == ListingApprovalStatus.APPROVED and not self.approved_by:
            raise ValueError("approved listings must record approved_by (human reviewer identifier)")
        return self


class CommerceCriticReview(BaseModel):
    opportunity_id: str
    recommendation: CommerceCriticRecommendation
    reason: str
    risk_flags: list[str] = Field(default_factory=list)


class Listing(BaseModel):
    listing_id: Optional[str] = None
    platform: Platform
    sku: str = Field(min_length=1)
    title: str = Field(min_length=1)
    price: float = Field(gt=0)
    quantity: int = Field(gt=0, default=1)
    status: ListingStatus = ListingStatus.DRAFT
    human_approved: bool = False
    approved_by: Optional[str] = None


class SupplierOrder(BaseModel):
    order_id: Optional[str] = None
    supplier_id: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    cost_per_unit: float = Field(gt=0)
    shipping_cost: float = Field(ge=0, default=0.0)
    total_cost: float = Field(gt=0)
    is_manual: bool = True
    status: SupplierOrderStatus = SupplierOrderStatus.MANUAL_PENDING
    ordered_by: Optional[str] = None
    notes: str = ""

    @model_validator(mode="after")
    def validate_manual_order(self):
        if not self.is_manual:
            raise ValueError("is_manual must be True (manual supplier ordering only)")
        return self


class ProductCandidate(BaseModel):
    id: Optional[int] = None
    candidate_id: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    title: str = Field(min_length=1)
    supplier_id: str = Field(min_length=1)
    target_platform: Platform = Platform.EBAY
    supplier_cost: float = Field(gt=0)
    target_price: float = Field(gt=0)
    shipping_cost: float = Field(default=0.0, ge=0)
    estimated_fee: float = Field(default=0.0, ge=0)
    estimated_profit: Optional[float] = None
    estimated_margin_pct: Optional[float] = None
    supplier_profit_status: SupplierProfitStatus = SupplierProfitStatus.NEEDS_SUPPLIER_DATA
    status: CandidateStatus = CandidateStatus.NEW
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_scout_opportunity(
        cls,
        opp: ProductScoutOpportunity,
        candidate_id: Optional[str] = None,
    ) -> "ProductCandidate":
        return cls(
            candidate_id=candidate_id or f"CAND-{opp.opportunity_id}",
            sku=opp.supplier_sku,
            title=opp.title,
            supplier_id=opp.supplier_id,
            target_platform=opp.target_platform,
            supplier_cost=opp.supplier_cost,
            target_price=opp.suggested_sale_price,
            shipping_cost=opp.estimated_shipping,
            estimated_fee=opp.estimated_platform_fee,
            estimated_profit=opp.estimated_net_profit,
            estimated_margin_pct=opp.estimated_margin_pct,
            status=CandidateStatus.NEW,
            created_at=opp.scouted_at,
            updated_at=opp.scouted_at,
        )


class SupplierCheckRecord(BaseModel):
    id: Optional[int] = None
    candidate_id: Optional[str] = None
    supplier_id: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    supplier_type: SupplierType
    is_valid: bool
    retail_dropshipping_blocked: bool = False
    reason: str
    passed_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: Optional[datetime] = None

    @classmethod
    def from_validation_result(
        cls,
        product: SupplierProduct,
        result: SupplierValidationResult,
        candidate_id: Optional[str] = None,
        checked_at: Optional[datetime] = None,
    ) -> "SupplierCheckRecord":
        return cls(
            candidate_id=candidate_id,
            supplier_id=product.supplier_id,
            sku=product.sku,
            supplier_type=product.supplier_type,
            is_valid=result.is_valid,
            retail_dropshipping_blocked=result.retail_dropshipping_blocked,
            reason=result.reason,
            passed_checks=result.passed_checks,
            warnings=result.warnings,
            checked_at=checked_at,
        )


class EBayListingDraft(BaseModel):
    draft_id: Optional[str] = None
    candidate_id: Optional[str] = None
    title: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    price: float = Field(gt=0)
    quantity: int = Field(default=1, gt=0)
    description: str = Field(min_length=1)
    category: str = Field(default="General Merchandise > Default Category")
    category_placeholder: str = Field(default="General Merchandise > Default Category")
    shipping: str = Field(default="Standard Shipping (Placeholder)")
    shipping_placeholder: str = Field(default="Standard Shipping (Placeholder)")
    supplier_reference: str = Field(min_length=1)
    expected_profit: float
    expected_margin: float
    status: DraftReviewStatus = DraftReviewStatus.DRAFT_CREATED
    human_approval_required: bool = True
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def SKU(self) -> str:
        return self.sku

    @model_validator(mode="before")
    @classmethod
    def sync_placeholders(cls, data):
        if isinstance(data, dict):
            if "category_placeholder" in data and "category" not in data:
                data["category"] = data["category_placeholder"]
            elif "category" in data and "category_placeholder" not in data:
                data["category_placeholder"] = data["category"]

            if "shipping_placeholder" in data and "shipping" not in data:
                data["shipping"] = data["shipping_placeholder"]
            elif "shipping" in data and "shipping_placeholder" not in data:
                data["shipping_placeholder"] = data["shipping"]
        return data

    @model_validator(mode="after")
    def validate_review_constraints(self):
        if not self.human_approval_required:
            raise ValueError("human_approval_required cannot be False (policy requirement)")
        if self.status == DraftReviewStatus.APPROVED_TO_PUBLISH and not self.reviewed_by:
            raise ValueError("approved drafts must record reviewed_by (human reviewer identifier)")
        return self

    @classmethod
    def from_candidate(
        cls,
        candidate: ProductCandidate,
        quantity: int = 1,
        description: Optional[str] = None,
        category: Optional[str] = None,
        shipping: Optional[str] = None,
    ) -> "EBayListingDraft":
        if candidate.status != CandidateStatus.APPROVED_FOR_LISTING:
            raise ValueError(
                f"Candidate '{candidate.candidate_id}' must be in APPROVED_FOR_LISTING status "
                f"to create an eBay listing draft (current status: {candidate.status.value})."
            )
        if candidate.supplier_profit_status != SupplierProfitStatus.VERIFIED_PROFITABLE:
            raise ValueError(
                f"Candidate '{candidate.candidate_id}' must have supplier/profit status "
                f"VERIFIED_PROFITABLE to create an eBay listing draft (current status: "
                f"{candidate.supplier_profit_status.value})."
            )

        cat = category or "General Merchandise > Default Category"
        shp = shipping or "Standard Shipping (Placeholder)"
        desc = (
            description
            or f"Brand new {candidate.title}. SKU: {candidate.sku}. Fast dispatch and satisfaction guaranteed."
        )
        exp_profit = (
            candidate.estimated_profit
            if candidate.estimated_profit is not None
            else round(
                candidate.target_price
                - candidate.supplier_cost
                - candidate.shipping_cost
                - candidate.estimated_fee,
                4,
            )
        )
        exp_margin = (
            candidate.estimated_margin_pct
            if candidate.estimated_margin_pct is not None
            else round(exp_profit / candidate.target_price, 4)
        )

        return cls(
            draft_id=f"DRAFT-EBAY-{candidate.sku}",
            candidate_id=candidate.candidate_id,
            title=candidate.title,
            sku=candidate.sku,
            price=candidate.target_price,
            quantity=quantity,
            description=desc,
            category=cat,
            category_placeholder=cat,
            shipping=shp,
            shipping_placeholder=shp,
            supplier_reference=candidate.supplier_id,
            expected_profit=exp_profit,
            expected_margin=exp_margin,
            status=DraftReviewStatus.DRAFT_CREATED,
            human_approval_required=True,
        )

    def to_seller_draft(self, agent_name: str = "seller_a") -> "SellerListingDraft":
        approval = (
            ListingApprovalStatus.APPROVED
            if self.status == DraftReviewStatus.APPROVED_TO_PUBLISH
            else (
                ListingApprovalStatus.REJECTED
                if self.status == DraftReviewStatus.REJECTED
                else ListingApprovalStatus.PENDING_APPROVAL
            )
        )
        return SellerListingDraft(
            agent_name=agent_name,
            sku=self.sku,
            title=self.title,
            description=self.description,
            target_platform=Platform.EBAY,
            proposed_price=self.price,
            strategy_notes=f"Expected profit: {self.expected_profit}, margin: {self.expected_margin:.2%}",
            human_approval_required=True,
            approval_status=approval,
            approved_by=self.reviewed_by if approval == ListingApprovalStatus.APPROVED else None,
            approved_at=self.reviewed_at if approval == ListingApprovalStatus.APPROVED else None,
        )


ListingDraft = EBayListingDraft
