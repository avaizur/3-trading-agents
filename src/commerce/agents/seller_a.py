from typing import Any, Optional

from src.commerce.policy_compatibility import match_supplier_to_ebay_policies
from src.commerce.storage import CommerceStore
from src.commerce.profit_engine import DEFAULT_MIN_MARGIN_PCT, calculate_profit
from src.commerce.schemas import (
    CommercialEvaluationResult,
    EBayListingDraft,
    EBayPolicySnapshot,
    PolicyCompatibilityStatus,
    ProductCandidate,
    ProductLane,
    SupplierBackedProduct,
    SupplierPolicyRules,
    SupplierProduct,
    SupplierType,
    clean_ebay_title,
)
from src.commerce.supplier_validator import validate_supplier


class CommercialAgent:
    """
    Agent 2: Commercial / Seller
    Evaluates commercial pricing, deterministic net margins (min 20%), supplier legitimacy,
    listing feasibility, and marketplace policy compatibility.
    """

    def __init__(self, db: Optional[CommerceStore] = None):
        self.db = db

    def evaluate(
        self,
        product: Any,
        target_price: Optional[float] = None,
        shipping: Optional[float] = None,
        platform_fee: Optional[float] = None,
        return_allowance: Optional[float] = None,
        rules: Optional[SupplierPolicyRules] = None,
        snapshot: Optional[EBayPolicySnapshot] = None,
    ) -> CommercialEvaluationResult:
        # Extract product attributes
        if isinstance(product, SupplierBackedProduct):
            sku = product.supplier_sku
            supplier_id = product.supplier_name
            title = product.product_name
            cost = product.supplier_cost
            lane = product.lane
            price = target_price if target_price is not None else product.market_price
            fee = platform_fee if platform_fee is not None else (product.platform_fees or 0.0)
            returns = return_allowance if return_allowance is not None else (product.return_allowance or 0.0)
        elif isinstance(product, ProductCandidate):
            sku = product.sku
            supplier_id = product.supplier_id
            title = product.title
            cost = product.supplier_cost
            lane = ProductLane.EVERGREEN
            price = target_price if target_price is not None else product.target_price
            fee = platform_fee if platform_fee is not None else product.estimated_fee
            returns = return_allowance if return_allowance is not None else 0.0
        elif isinstance(product, dict):
            sku = product.get("supplier_sku") or product.get("sku", "UNKNOWN")
            supplier_id = product.get("supplier_name") or product.get("supplier_id", "UNKNOWN_SUPPLIER")
            title = product.get("product_name") or product.get("title", "Unknown Product")
            cost = float(product.get("supplier_cost") or product.get("cost", 0.0))
            lane = product.get("lane", ProductLane.EVERGREEN)
            price = target_price if target_price is not None else product.get("market_price") or product.get("target_price")
            fee = platform_fee if platform_fee is not None else product.get("platform_fees") or product.get("estimated_fee", 0.0)
            returns = return_allowance if return_allowance is not None else product.get("return_allowance", 0.0)
        else:
            sku = getattr(product, "supplier_sku", getattr(product, "sku", "UNKNOWN"))
            supplier_id = getattr(product, "supplier_name", getattr(product, "supplier_id", "UNKNOWN_SUPPLIER"))
            title = getattr(product, "product_name", getattr(product, "title", "Unknown Product"))
            cost = float(getattr(product, "supplier_cost", getattr(product, "cost", 0.0)))
            lane = getattr(product, "lane", ProductLane.EVERGREEN)
            price = target_price if target_price is not None else getattr(product, "market_price", getattr(product, "target_price", None))
            fee = platform_fee if platform_fee is not None else getattr(product, "platform_fees", getattr(product, "estimated_fee", 0.0))
            returns = return_allowance if return_allowance is not None else getattr(product, "return_allowance", 0.0)

        shipping_cost = shipping if shipping is not None else getattr(product, "shipping_cost", 0.0)
        sale_price = float(price) if price is not None else 0.0

        reasons: list[str] = []

        # 1. Validate supplier integrity (anti-retail dropshipping)
        supplier_prod = SupplierProduct(
            supplier_id=supplier_id,
            sku=sku,
            title=title,
            supplier_type=SupplierType.WHOLESALE,
            cost=cost if cost > 0 else 1.0,
            shipping_cost=shipping_cost,
            allows_reselling=True,
            supplier_name=supplier_id,
        )
        validation = validate_supplier(supplier_prod)
        supplier_valid = validation.is_valid
        if not supplier_valid:
            reasons.append(f"Supplier validation rejected: {validation.reason}")
        else:
            reasons.append("Supplier validation passed: non-retail wholesale sourcing confirmed.")

        # 2. Deterministic profit & margin calculation (immutable 20% rule)
        if sale_price <= 0:
            profit_decision = calculate_profit(
                supplier_cost=cost,
                shipping=shipping_cost,
                platform_fee=fee,
                return_buffer=returns,
                sale_price=0.01,
                min_margin_pct=DEFAULT_MIN_MARGIN_PCT,
            )
            meets_margin = False
            reasons.append("Missing or non-positive marketplace sale price.")
        else:
            profit_decision = calculate_profit(
                supplier_cost=cost,
                shipping=shipping_cost,
                platform_fee=fee,
                return_buffer=returns,
                sale_price=sale_price,
                min_margin_pct=DEFAULT_MIN_MARGIN_PCT,
            )
            meets_margin = profit_decision.allowed
            reasons.append(
                f"Economics: profit £{profit_decision.net_profit:.2f}, "
                f"margin {profit_decision.margin_pct:.2%} "
                f"(min required: {profit_decision.min_margin_pct:.2%})."
            )

        # 3. Policy compatibility
        policy_compatible = True
        policy_notes: Optional[str] = None
        if rules and snapshot:
            compat_result = match_supplier_to_ebay_policies(rules, snapshot)
            policy_compatible = compat_result.status == PolicyCompatibilityStatus.MATCHED
            policy_notes = compat_result.reason
            reasons.append(f"Policy compatibility: {policy_notes}.")
        elif rules:
            if not rules.blind_ship:
                policy_compatible = False
                policy_notes = "Supplier does not support blind shipping."
                reasons.append("Policy mismatch: supplier cannot blind-ship.")
            else:
                policy_notes = "Supplier blind shipping confirmed."
                reasons.append("Policy check: supplier supports blind shipping.")

        # 4. Listing draft attributes
        draft_title = clean_ebay_title(title, max_length=80)
        if sku.startswith("PET-"):
            category = "Pet Supplies"
        elif lane == ProductLane.SEASONAL or (isinstance(lane, str) and lane == "SEASONAL"):
            category = "Home, Furniture & DIY > Seasonal Decorations"
        else:
            category = "General Merchandise > Default Category"

        shipping_service = "Tracked 2 Business Day" if rules and "TRACKED_2_BUSINESS_DAY" in rules.shipping_services else "Standard Tracked Delivery"

        # 5. Commercial Recommendation
        if meets_margin and supplier_valid and policy_compatible:
            recommendation = "PROCEED"
            reasons.append("Commercial recommendation: PROCEED. Unit economics and policy rules satisfied.")
        else:
            recommendation = "REJECT"
            reasons.append("Commercial recommendation: REJECT. Economics or operational policy criteria not met.")

        return CommercialEvaluationResult(
            sku=sku,
            proposed_price=sale_price,
            supplier_cost=cost,
            shipping=shipping_cost,
            platform_fee=fee,
            return_buffer=returns,
            total_cost=profit_decision.total_cost,
            expected_profit=profit_decision.net_profit,
            expected_margin=profit_decision.margin_pct,
            meets_minimum_margin=meets_margin,
            supplier_valid=supplier_valid,
            policy_compatible=policy_compatible,
            policy_notes=policy_notes,
            draft_title=draft_title,
            category=category,
            shipping_service=shipping_service,
            recommendation=recommendation,
            reasons=reasons,
        )


def run(product: Any = None, *args: Any, **kwargs: Any) -> Any:
    if product is None:
        return "Seller A not connected yet"
    return CommercialAgent().evaluate(product, *args, **kwargs)


def create_ebay_draft(
    candidate: ProductCandidate,
    quantity: int = 1,
    description: Optional[str] = None,
    category: Optional[str] = None,
    shipping: Optional[str] = None,
) -> EBayListingDraft:
    """
    Seller A (eBay Agent) conversion function:
    Converts a candidate in APPROVED_FOR_LISTING status into an eBay listing draft.
    """
    return EBayListingDraft.from_candidate(
        candidate=candidate,
        quantity=quantity,
        description=description,
        category=category,
        shipping=shipping,
    )

