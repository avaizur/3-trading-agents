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
