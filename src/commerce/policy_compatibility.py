from src.commerce.schemas import (
    EBayPolicySnapshot, PolicyCompatibilityResult, PolicyCompatibilityStatus,
    SupplierPolicyRules,
)


def match_supplier_to_ebay_policies(
    rules: SupplierPolicyRules, snapshot: EBayPolicySnapshot
) -> PolicyCompatibilityResult:
    """Select an existing compatible policy set without changing eBay state."""
    failures: list[str] = []
    if not rules.blind_ship:
        failures.append("supplier does not support blind shipping")
    fulfillment = None
    for policy in snapshot.fulfillment_policies:
        reasons = []
        if policy.handling_time_days < rules.dispatch_time_days:
            reasons.append("handling time is shorter than supplier dispatch time")
        wanted = {s.casefold() for s in rules.shipping_services}
        offered = {s.casefold() for s in policy.shipping_services}
        if wanted and not wanted.intersection(offered):
            reasons.append("shipping service is incompatible")
        if rules.remote_surcharge > 0 and not policy.excluded_regions:
            reasons.append("remote surcharge is not protected by excluded regions")
        if not reasons:
            fulfillment = policy
            break
        failures.extend(f"fulfillment {policy.policy_id}: {reason}" for reason in reasons)

    return_policy = next((p for p in snapshot.return_policies if p.returns_accepted and
                          p.return_shipping_cost_payer == rules.return_postage), None)
    if return_policy is None:
        failures.append("no returns policy matches return acceptance and return postage payer")
    payment = snapshot.payment_policies[0] if snapshot.payment_policies else None
    if payment is None:
        failures.append("no payment policy is available")
    location = next((p for p in snapshot.inventory_locations if p.status.upper() == "ENABLED"), None)
    if location is None:
        failures.append("no enabled inventory location is available")

    if failures or fulfillment is None or return_policy is None or payment is None or location is None:
        return PolicyCompatibilityResult(
            status=PolicyCompatibilityStatus.MISMATCH,
            reason="; ".join(dict.fromkeys(failures)) or "no compatible fulfillment policy",
            fulfillment_policy_id=fulfillment.policy_id if fulfillment else None,
            return_policy_id=return_policy.policy_id if return_policy else None,
            payment_policy_id=payment.policy_id if payment else None,
            inventory_location_key=location.merchant_location_key if location else None,
        )
    rma_note = "; supplier RMA required" if rules.rma_required else ""
    return PolicyCompatibilityResult(
        status=PolicyCompatibilityStatus.MATCHED,
        reason=f"existing eBay policies satisfy supplier rules{rma_note}",
        fulfillment_policy_id=fulfillment.policy_id, return_policy_id=return_policy.policy_id,
        payment_policy_id=payment.policy_id, inventory_location_key=location.merchant_location_key,
    )
