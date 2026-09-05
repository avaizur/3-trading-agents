from src.commerce.adapters.amazon import AmazonAdapter, PlatformDisabledError
from src.commerce.adapters.ebay import EBayAdapter
from src.commerce.adapters.supplier_base import BaseSupplierAdapter
from src.commerce.agents.critic import run as run_critic
from src.commerce.agents.product_scout import run as run_product_scout
from src.commerce.agents.seller_a import run as run_seller_a
from src.commerce.agents.seller_b import run as run_seller_b
from src.commerce.database import (
    COMMERCE_SCHEMA,
    CommerceDatabase,
    init_commerce_database,
)
from src.commerce.profit_engine import (
    DEFAULT_MIN_MARGIN_PCT,
    calculate_profit,
    evaluate_profit_from_input,
)
from src.commerce.queue import (
    VALID_DRAFT_STATUS_TRANSITIONS,
    VALID_STATUS_TRANSITIONS,
    CandidateQueue,
    CommerceQueue,
    InvalidDraftStatusTransitionError,
    InvalidStatusTransitionError,
    ProductCandidateQueue,
    ProductQueue,
)
from src.commerce.schemas import (
    CandidateStatus,
    CommerceCriticRecommendation,
    CommerceCriticReview,
    DraftReviewStatus,
    EBayListingDraft,
    HumanReviewStatus,
    Listing,
    ListingApprovalStatus,
    ListingDraft,
    ListingDraftStatus,
    ListingStatus,
    Platform,
    PlatformStatus,
    ProductCandidate,
    ProductQueueStatus,
    ProductScoutOpportunity,
    ProfitCalculationInput,
    ProfitDecision,
    SellerListingDraft,
    SupplierCheckRecord,
    SupplierProfitStatus,
    SupplierOrder,
    SupplierOrderStatus,
    SupplierProduct,
    SupplierType,
    SupplierValidationResult,
    SupplierVerificationStatus,
)
from src.commerce.supplier_matching import (
    ManualSupplierInput,
    ManualSupplierMatcher,
    SupplierMatchInterface,
    SupplierMatchResult,
    verify_manual_supplier_match,
)
from src.commerce.seller_a import create_ebay_draft
from src.commerce.supplier_validator import (
    validate_supplier,
    validate_supplier_product,
)

__all__ = [
    # Schemas
    "Platform",
    "PlatformStatus",
    "SupplierType",
    "ListingApprovalStatus",
    "ListingStatus",
    "SupplierOrderStatus",
    "CommerceCriticRecommendation",
    "CandidateStatus",
    "ProductQueueStatus",
    "DraftReviewStatus",
    "HumanReviewStatus",
    "ListingDraftStatus",
    "SupplierProduct",
    "SupplierValidationResult",
    "SupplierVerificationStatus",
    "SupplierProfitStatus",
    "ManualSupplierInput",
    "SupplierMatchResult",
    "SupplierMatchInterface",
    "ManualSupplierMatcher",
    "verify_manual_supplier_match",
    "ProfitCalculationInput",
    "ProfitDecision",
    "ProductScoutOpportunity",
    "ProductCandidate",
    "SupplierCheckRecord",
    "SellerListingDraft",
    "EBayListingDraft",
    "ListingDraft",
    "CommerceCriticReview",
    "Listing",
    "SupplierOrder",
    # Database & Persistence
    "COMMERCE_SCHEMA",
    "CommerceDatabase",
    "init_commerce_database",
    # Queue Model
    "CandidateQueue",
    "ProductCandidateQueue",
    "CommerceQueue",
    "ProductQueue",
    "InvalidStatusTransitionError",
    "VALID_STATUS_TRANSITIONS",
    "InvalidDraftStatusTransitionError",
    "VALID_DRAFT_STATUS_TRANSITIONS",
    # Profit Engine
    "DEFAULT_MIN_MARGIN_PCT",
    "calculate_profit",
    "evaluate_profit_from_input",
    # Supplier Validator
    "validate_supplier",
    "validate_supplier_product",
    # Adapters
    "BaseSupplierAdapter",
    "EBayAdapter",
    "AmazonAdapter",
    "PlatformDisabledError",
    # Agents
    "run_product_scout",
    "run_seller_a",
    "run_seller_b",
    "run_critic",
    "create_ebay_draft",
]
