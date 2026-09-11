"""Import the locked Go Dropship product batch into the commerce database."""

import argparse
from typing import Sequence

from src.commerce.database import CommerceDatabase
from src.commerce.schemas import ProductLane, SupplierBackedProduct


LOCKED_SUPPLIER_PRODUCTS = (
    SupplierBackedProduct(
        supplier_name="Go Dropship", supplier_sku="PET-73110",
        product_name="2-in-1 pet feeder", supplier_cost=8.64,
        lane=ProductLane.EVERGREEN,
    ),
    SupplierBackedProduct(
        supplier_name="Go Dropship", supplier_sku="PET-73135",
        product_name="anti-splash cat litter box", supplier_cost=12.68,
        lane=ProductLane.EVERGREEN,
    ),
    SupplierBackedProduct(
        supplier_name="Go Dropship", supplier_sku="PET-73719",
        product_name="large soft pet carrier", supplier_cost=9.65,
        lane=ProductLane.EVERGREEN,
    ),
    SupplierBackedProduct(
        supplier_name="Go Dropship", supplier_sku="HOM-55216",
        product_name="6pc Christmas feather ornaments", supplier_cost=3.94,
        lane=ProductLane.SEASONAL,
    ),
)


def import_locked_products(db_path: str = "data/commerce.db") -> list[SupplierBackedProduct]:
    return CommerceDatabase(db_path).import_supplier_backed_products(
        [product.model_copy(deep=True) for product in LOCKED_SUPPLIER_PRODUCTS]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/commerce.db", help="SQLite database path")
    args = parser.parse_args(argv)
    products = import_locked_products(args.db)
    print(f"Imported {len(products)} locked supplier-backed products.")
    print("Profitability pending validated market price, fees, and return allowance.")
    print("No products were approved or published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
