from typing import Optional

from src.commerce.adapters.supplier_base import BaseSupplierAdapter
from src.commerce.godropship_discovery import (
    discover_products,
    fetch_product_snapshot,
    save_new_products,
)
from src.commerce.schemas import SupplierProduct, SupplierType


class GoDropshipAdapter(BaseSupplierAdapter):
    """
    Go Dropship supplier adapter.

    Normalizes the existing Go Dropship discovery/storage implementation
    behind the common supplier interface.
    """

    def __init__(self, store=None):
        super().__init__(
            supplier_id="go_dropship",
            supplier_name="Go Dropship",
        )
        self.store = store

    def _require_store(self):
        if self.store is None:
            raise RuntimeError(
                "GoDropshipAdapter requires a commerce store for product lookup."
            )

    def get_product(self, sku: str) -> Optional[SupplierProduct]:
        self._require_store()

        product = self.store.get_supplier_backed_product(
            self.supplier_name,
            sku,
        )

        if product is None:
            return None

        return SupplierProduct(
            supplier_id=self.supplier_id,
            supplier_name=self.supplier_name,
            sku=product.supplier_sku,
            title=product.product_name,
            supplier_type=SupplierType.WHOLESALE,
            cost=product.supplier_cost,
            shipping_cost=0.0,
            inventory_count=product.supplier_stock,
            allows_reselling=True,
            supplier_url=product.source_url,
        )

    def refresh_product(self, sku: str) -> Optional[SupplierProduct]:
        """
        Fetch current supplier cost and stock for an already-known product.
        """
        self._require_store()

        current = self.store.get_supplier_backed_product(
            self.supplier_name,
            sku,
        )

        if current is None or not current.source_url:
            return None

        snapshot = fetch_product_snapshot(
            current.source_url,
        )

        if snapshot is None:
            return None

        if snapshot.sku.casefold() != sku.casefold():
            raise ValueError(
                "Supplier page SKU does not match requested SKU."
            )

        return SupplierProduct(
            supplier_id=self.supplier_id,
            supplier_name=self.supplier_name,
            sku=snapshot.sku,
            title=snapshot.title,
            supplier_type=SupplierType.WHOLESALE,
            cost=snapshot.cost,
            shipping_cost=0.0,
            inventory_count=snapshot.stock,
            allows_reselling=True,
            supplier_url=snapshot.url,
        )

    def check_inventory(self, sku: str) -> int:
        product = self.get_product(sku)

        if product is None or product.inventory_count is None:
            return 0

        return product.inventory_count

    def discover(
        self,
        *,
        max_products: int = 20,
        request_pause_seconds: float = 0.15,
    ):
        return discover_products(
            max_products=max_products,
            request_pause_seconds=request_pause_seconds,
        )

    def discover_and_save(
        self,
        *,
        max_products: int = 20,
        request_pause_seconds: float = 0.15,
    ) -> dict:
        self._require_store()

        products = self.discover(
            max_products=max_products,
            request_pause_seconds=request_pause_seconds,
        )

        return save_new_products(
            self.store,
            products,
        )

    def test_connection(self) -> dict:
        result = super().test_connection()
        result["mode"] = "public_catalog"
        result["supports_discovery"] = True
        result["automated_ordering"] = False
        return result
