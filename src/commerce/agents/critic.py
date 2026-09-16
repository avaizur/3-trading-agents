from datetime import date
from typing import Any, Optional

from src.commerce.profit_engine import DEFAULT_MIN_MARGIN_PCT, calculate_profit
from src.commerce.schemas import (
    CommercialEvaluationResult,
    CommerceCriticRecommendation,
    CriticEvaluationResult,
    ProductLane,
    ScoutEvaluationResult,
    SupplierBackedProduct,
    SupplierPolicyRules,
)


class CommerceCriticAgent:
    """
    Agent 3: Critic / Risk
    Stress tests assumptions, price sensitivity, fee shocks, supplier risk,
    policy compatibility, return allowances, and seasonal timing.
    Outputs CONTINUE, CAUTION, or BLOCK.
    """

    def __init__(self, db=None):
        self.db = db

    def evaluate(
        self,
        product: Any,
        commercial_eval: CommercialEvaluationResult,
        scout_eval: Optional[ScoutEvaluationResult] = None,
        rules: Optional[SupplierPolicyRules] = None,
        as_of: Optional[date] = None,
    ) -> CriticEvaluationResult:
        sku = commercial_eval.sku
        sale_price = commercial_eval.proposed_price
        supplier_cost = commercial_eval.supplier_cost
        shipping = commercial_eval.shipping
        fee = commercial_eval.platform_fee
        return_buffer = commercial_eval.return_buffer
        current_margin = commercial_eval.expected_margin

        margin_cushion = round(current_margin - DEFAULT_MIN_MARGIN_PCT, 4)
        risk_flags: list[str] = []
        stress_tests: dict[str, Any] = {}
        risk_score = 15

        # 1. Base margin check
        if current_margin < DEFAULT_MIN_MARGIN_PCT:
            risk_flags.append(
                f"CRITICAL: Baseline margin {current_margin:.2%} is below the 20.00% safety floor."
            )
            risk_score += 60

        # 2. Price erosion stress tests (-5% and -10%)
        if sale_price > 0:
            price_minus_5 = round(sale_price * 0.95, 2)
            dec_5 = calculate_profit(
                supplier_cost=supplier_cost,
                shipping=shipping,
                platform_fee=fee,
                return_buffer=return_buffer,
                sale_price=price_minus_5,
            )
            stress_tests["price_minus_5pct_price"] = price_minus_5
            stress_tests["price_minus_5pct_margin"] = dec_5.margin_pct
            stress_tests["price_minus_5pct_profit"] = dec_5.net_profit
            if dec_5.margin_pct < DEFAULT_MIN_MARGIN_PCT:
                risk_flags.append(
                    f"PRICE_SENSITIVITY: A 5% price reduction (£{price_minus_5:.2f}) "
                    f"drops margin to {dec_5.margin_pct:.2%}, breaching 20%."
                )
                risk_score += 20

            price_minus_10 = round(sale_price * 0.90, 2)
            dec_10 = calculate_profit(
                supplier_cost=supplier_cost,
                shipping=shipping,
                platform_fee=fee,
                return_buffer=return_buffer,
                sale_price=price_minus_10,
            )
            stress_tests["price_minus_10pct_price"] = price_minus_10
            stress_tests["price_minus_10pct_margin"] = dec_10.margin_pct
            stress_tests["price_minus_10pct_profit"] = dec_10.net_profit

        # 3. Cost / Shipping shock stress tests (+£1.00 shipping, +10% supplier cost)
        dec_ship = calculate_profit(
            supplier_cost=supplier_cost,
            shipping=shipping + 1.00,
            platform_fee=fee,
            return_buffer=return_buffer,
            sale_price=sale_price if sale_price > 0 else 10.0,
        )
        stress_tests["shipping_plus_1gbp_margin"] = dec_ship.margin_pct
        if sale_price > 0 and dec_ship.margin_pct < DEFAULT_MIN_MARGIN_PCT:
            risk_flags.append(
                f"SHIPPING_SHOCK: A £1.00 fulfillment increase drops margin to {dec_ship.margin_pct:.2%}."
            )
            risk_score += 15

        if 0 <= margin_cushion < 0.02 and current_margin >= DEFAULT_MIN_MARGIN_PCT:
            risk_flags.append(
                f"THIN_CUSHION: Margin cushion is only {margin_cushion:.2%} above safety threshold."
            )
            risk_score += 15

        # 4. Return risk & category traits
        title = ""
        if isinstance(product, SupplierBackedProduct):
            title = product.product_name
        elif hasattr(product, "title"):
            title = product.title
        elif isinstance(product, dict):
            title = product.get("product_name") or product.get("title", "")
        title_lower = title.lower()

        # Fragile merchandise
        if any(term in title_lower for term in ("glass", "ceramic", "porcelain", "mirror", "fragile")):
            risk_flags.append("TRANSIT_RISK: Fragile product vulnerable to transit damage claims.")
            risk_score += 15
            if return_buffer < (sale_price * 0.05):
                risk_flags.append("INSUFFICIENT_RETURN_BUFFER: Return allowance is under 5% for fragile item.")
                risk_score += 10

        # Apparel / footwear sizing
        if any(term in title_lower for term in ("clothing", "apparel", "shirt", "shoe", "trainer", "boot")):
            risk_flags.append("SIZING_RISK: Apparel/footwear category has high sizing return rates.")
            risk_score += 20

        # Electronics
        if any(term in title_lower for term in ("laptop", "tablet", "drone", "camera", "phone")):
            risk_flags.append("TECH_RISK: Electronic product subject to technical defect disputes.")
            risk_score += 15

        # 5. Supplier and policy constraints
        if rules:
            if not rules.blind_ship:
                risk_flags.append("POLICY_BLOCK: Supplier does not support blind shipping.")
                risk_score += 50
            if rules.rma_required:
                risk_flags.append("OPERATIONAL_NOTE: Supplier requires RMA for return processing.")
                risk_score += 5
            if getattr(rules, "return_postage", None) and str(rules.return_postage).upper() == "BUYER":
                risk_flags.append("BUYER_POSTAGE_FRICTION: Buyer-paid returns may increase negative feedback risk.")
                risk_score += 5
            if rules.dispatch_time_days > 2:
                risk_flags.append(f"DISPATCH_DELAY: Supplier dispatch time is {rules.dispatch_time_days} days.")
                risk_score += 10
        elif not commercial_eval.policy_compatible:
            risk_flags.append(f"POLICY_MISMATCH: {commercial_eval.policy_notes}")
            risk_score += 30

        # 6. Seasonal timing
        if scout_eval:
            if scout_eval.seasonal_window_status == "CLOSED":
                risk_flags.append(
                    f"TIMING_BLOCK: Seasonal window for {scout_eval.seasonal_event or 'event'} is CLOSED."
                )
                risk_score += 50
            elif scout_eval.confidence < 0.65:
                risk_flags.append("EVIDENCE_WEAK: Low confidence in marketplace search evidence.")
                risk_score += 15

        # 7. Final Recommendation
        risk_score = min(100, max(0, risk_score))

        if (
            current_margin < DEFAULT_MIN_MARGIN_PCT
            or (rules and not rules.blind_ship)
            or (scout_eval and scout_eval.seasonal_window_status == "CLOSED")
            or risk_score >= 80
        ):
            rec = CommerceCriticRecommendation.BLOCK
            reasoning = "Critic recommendation: BLOCK. Critical safety breach or excessive risk detected."
        elif risk_flags or risk_score >= 35:
            rec = CommerceCriticRecommendation.CAUTION
            reasoning = f"Critic recommendation: CAUTION. {len(risk_flags)} risk factor(s) identified."
        else:
            rec = CommerceCriticRecommendation.CONTINUE
            reasoning = "Critic recommendation: CONTINUE. Unit economics robust with manageable risk profile."

        return CriticEvaluationResult(
            sku=sku,
            recommendation=rec,
            risk_score=risk_score,
            margin_cushion=margin_cushion,
            risk_flags=risk_flags,
            stress_test_results=stress_tests,
            reasoning=reasoning,
        )


def run(product: Any = None, *args: Any, **kwargs: Any) -> Any:
    if product is None:
        return "Commerce Critic not connected yet"
    return CommerceCriticAgent().evaluate(product, *args, **kwargs)

