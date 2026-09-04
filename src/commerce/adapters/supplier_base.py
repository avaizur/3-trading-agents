from abc import ABC, abstractmethod
from typing import Optional
import uuid

from src.commerce.schemas import (
    SupplierOrder,
    SupplierOrderStatus,
    SupplierProduct,
)


class BaseSupplierAdapter(ABC):
    """
    Abstract base adapter for supplier interactions.
    Enforces Phase 1 manual supplier ordering constraint.
    """

    def __init__(self, supplier_id: str, supplier_name: str):
        self.supplier_id = supplier_id
        self.supplier_name = supplier_name
        self.is_connected = True

    @abstractmethod
    def get_product(self, sku: str) -> Optional[SupplierProduct]:
        """Retrieve supplier product metadata and pricing."""
        raise NotImplementedError

    @abstractmethod
    def check_inventory(self, sku: str) -> int:
        """Check supplier inventory level."""
        raise NotImplementedError

    def create_manual_order(
        self,
        sku: str,
        quantity: int,
        cost_per_unit: float,
        shipping_cost: float = 0.0,
        ordered_by: Optional[str] = None,
        notes: str = "",
    ) -> SupplierOrder:
        """
        Creates a manual supplier order record.
        Orders require human execution; automated placement is blocked.
        """
        if quantity <= 0:
            raise ValueError("Order quantity must be greater than zero")
        if cost_per_unit <= 0:
            raise ValueError("Cost per unit must be greater than zero")
        if shipping_cost < 0:
            raise ValueError("Shipping cost cannot be negative")

        order_id = f"MANUAL-ORD-{uuid.uuid4().hex[:8].upper()}"
        total_cost = round((cost_per_unit * quantity) + shipping_cost, 2)

        return SupplierOrder(
            order_id=order_id,
            supplier_id=self.supplier_id,
            sku=sku,
            quantity=quantity,
            cost_per_unit=cost_per_unit,
            shipping_cost=shipping_cost,
            total_cost=total_cost,
            is_manual=True,
            status=SupplierOrderStatus.MANUAL_PENDING,
            ordered_by=ordered_by,
            notes=notes,
        )

    def auto_fulfill_order(self, *args, **kwargs):
        """
        Explicitly blocked by policy: manual supplier ordering only.
        """
        raise NotImplementedError(
            "Automated order placement is disabled. Phase 1 requires manual supplier ordering only."
        )

    def test_connection(self) -> dict:
        """Health check for supplier integration."""
        return {
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "status": "HEALTHY" if self.is_connected else "DISCONNECTED",
            "mode": "offline_placeholder",
        }
