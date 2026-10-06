"""CJdropshipping operational policy for 3 Trading Agents.

CJ is a restricted secondary supplier.

Rules:
- buyer returns are handled by us in the UK
- resaleable returns become local Avaiizur inventory
- supplier disputes/RMA are still required for damaged/wrong items
- never auto-order
- use a higher return reserve than GoDropship
"""

from src.commerce.schemas import (
    ReturnPostagePayer,
    ReturnRoute,
    SupplierPolicyRules,
)

CJ_RETURN_RESERVE_RATE = 0.15


def cj_supplier_policy() -> SupplierPolicyRules:
    return SupplierPolicyRules(
        supplier_id="cjdropshipping",
        dispatch_time_days=5,
        shipping_services=["Standard Tracked Delivery"],
        remote_surcharge=0.0,
        blind_ship=True,
        return_route=ReturnRoute.SELLER,
        rma_required=True,
        return_postage=ReturnPostagePayer.SELLER,
        supplier_fault_resolution=(
            "CJ dispute first for damaged/wrong/missing items. "
            "Buyer returns are handled by seller in the UK. "
            "Unused/resaleable returns may become local Avaiizur inventory. "
            "Do not automatically return buyer items to CJ China."
        ),
    )
