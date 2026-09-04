import re
from typing import Optional

from src.commerce.schemas import (
    SupplierProduct,
    SupplierType,
    SupplierValidationResult,
)

# Known retail marketplaces forbidden for dropshipping / sourcing
DISALLOWED_RETAIL_PATTERNS = [
    r"\bamazon\b",
    r"\bwalmart\b",
    r"\btarget\b",
    r"\bebay\b",
    r"\baliexpress\b",
    r"\bbestbuy\b",
    r"\bcostco\b",
    r"\bhome\s*depot\b",
]


def validate_supplier(product: SupplierProduct) -> SupplierValidationResult:
    """
    Validates a supplier product according to commerce rules:
    1. Strict prohibition of retail-to-retail dropshipping.
    2. Sourcing must come from wholesale, distributor, manufacturer, or verified direct B2B.
    3. Reselling permissions and terms must be verified.
    4. Positive unit economics prerequisites (positive cost, non-negative shipping).
    5. Inventory availability (cannot be out of stock).
    """
    passed_checks: list[str] = []
    warnings: list[str] = []

    # Check 1: Supplier type check (no retail dropshipping)
    if product.supplier_type == SupplierType.RETAIL:
        return SupplierValidationResult(
            is_valid=False,
            reason="Retail-to-retail dropshipping is strictly prohibited. Sourcing must be wholesale, distributor, or manufacturer.",
            supplier_type=product.supplier_type,
            retail_dropshipping_blocked=True,
            passed_checks=passed_checks,
            warnings=warnings,
        )
    passed_checks.append("supplier_type_non_retail")

    # Check 2: Inspect supplier name or URL for disallowed retail sources
    supplier_identifiers = [
        product.supplier_id or "",
        product.supplier_name or "",
        product.supplier_url or "",
    ]
    combined_identity = " ".join(supplier_identifiers).lower()
    for pattern in DISALLOWED_RETAIL_PATTERNS:
        if re.search(pattern, combined_identity):
            return SupplierValidationResult(
                is_valid=False,
                reason=f"Supplier identity matched prohibited retail marketplace pattern '{pattern}'. Retail dropshipping is prohibited.",
                supplier_type=product.supplier_type,
                retail_dropshipping_blocked=True,
                passed_checks=passed_checks,
                warnings=warnings,
            )
    passed_checks.append("no_retail_marketplace_detected")

    # Check 3: Reselling permission
    if not product.allows_reselling:
        return SupplierValidationResult(
            is_valid=False,
            reason="Supplier terms do not authorize commercial reselling.",
            supplier_type=product.supplier_type,
            retail_dropshipping_blocked=False,
            passed_checks=passed_checks,
            warnings=warnings,
        )
    passed_checks.append("reselling_authorized")

    # Check 4: Cost checks
    if product.cost <= 0:
        return SupplierValidationResult(
            is_valid=False,
            reason="Supplier cost must be greater than zero.",
            supplier_type=product.supplier_type,
            retail_dropshipping_blocked=False,
            passed_checks=passed_checks,
            warnings=warnings,
        )
    passed_checks.append("valid_cost")

    if product.shipping_cost < 0:
        return SupplierValidationResult(
            is_valid=False,
            reason="Supplier shipping cost cannot be negative.",
            supplier_type=product.supplier_type,
            retail_dropshipping_blocked=False,
            passed_checks=passed_checks,
            warnings=warnings,
        )
    passed_checks.append("valid_shipping_cost")

    # Check 5: Inventory count
    if product.inventory_count is not None and product.inventory_count <= 0:
        return SupplierValidationResult(
            is_valid=False,
            reason="Supplier product is out of stock.",
            supplier_type=product.supplier_type,
            retail_dropshipping_blocked=False,
            passed_checks=passed_checks,
            warnings=warnings,
        )
    if product.inventory_count is not None:
        passed_checks.append("inventory_in_stock")

    # Check 6: Lead time checks
    if product.lead_time_days is not None:
        if product.lead_time_days < 0:
            return SupplierValidationResult(
                is_valid=False,
                reason="Lead time cannot be negative.",
                supplier_type=product.supplier_type,
                retail_dropshipping_blocked=False,
                passed_checks=passed_checks,
                warnings=warnings,
            )
        if product.lead_time_days > 45:
            warnings.append("Extended lead time (>45 days) requires customer expectation management.")
        passed_checks.append("valid_lead_time")

    return SupplierValidationResult(
        is_valid=True,
        reason="Supplier product passed all validation checks.",
        supplier_type=product.supplier_type,
        retail_dropshipping_blocked=False,
        passed_checks=passed_checks,
        warnings=warnings,
    )


def validate_supplier_product(product: SupplierProduct) -> tuple[bool, str]:
    """Convenience tuple return helper matching data validator conventions."""
    result = validate_supplier(product)
    return result.is_valid, result.reason
