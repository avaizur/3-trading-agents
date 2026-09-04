from src.commerce.schemas import SupplierProduct, SupplierType
from src.commerce.supplier_validator import (
    validate_supplier,
    validate_supplier_product,
)


def test_wholesale_supplier_passes_validation():
    product = SupplierProduct(
        supplier_id="WHOLESALE-001",
        sku="SKU-STEEL-10",
        title="Stainless Steel Bottle",
        supplier_type=SupplierType.WHOLESALE,
        cost=15.0,
        shipping_cost=3.0,
        inventory_count=100,
        lead_time_days=5,
        allows_reselling=True,
    )
    result = validate_supplier(product)
    assert result.is_valid is True
    assert result.retail_dropshipping_blocked is False
    assert "supplier_type_non_retail" in result.passed_checks


def test_distributor_and_manufacturer_pass():
    for stype in (SupplierType.DISTRIBUTOR, SupplierType.MANUFACTURER, SupplierType.DIRECT):
        prod = SupplierProduct(
            supplier_id="SUP-VALID-1",
            sku="SKU-ABC",
            title="Industrial Widget",
            supplier_type=stype,
            cost=20.0,
            shipping_cost=2.0,
            inventory_count=50,
            lead_time_days=2,
            allows_reselling=True,
        )
        result = validate_supplier(prod)
        assert result.is_valid is True


def test_retail_supplier_blocked_as_dropshipping():
    product = SupplierProduct(
        supplier_id="RETAIL-STORE-1",
        sku="SKU-RETAIL-01",
        title="Retail Item From Store",
        supplier_type=SupplierType.RETAIL,
        cost=15.0,
        shipping_cost=3.0,
        inventory_count=100,
        allows_reselling=True,
    )
    result = validate_supplier(product)
    assert result.is_valid is False
    assert result.retail_dropshipping_blocked is True
    assert "Retail-to-retail dropshipping is strictly prohibited" in result.reason


def test_retail_marketplace_identifier_blocked():
    # Attempting to label Amazon as WHOLESALE is caught and blocked
    product = SupplierProduct(
        supplier_id="AMAZON-PRIME-SELLER",
        sku="SKU-AMZ-01",
        title="Widget bought off Amazon",
        supplier_type=SupplierType.WHOLESALE,
        supplier_name="Amazon Retail Services",
        supplier_url="https://www.amazon.com/dp/B000TEST",
        cost=15.0,
        shipping_cost=0.0,
        inventory_count=20,
        allows_reselling=True,
    )
    result = validate_supplier(product)
    assert result.is_valid is False
    assert result.retail_dropshipping_blocked is True
    assert "prohibited retail marketplace" in result.reason


def test_supplier_reselling_not_allowed():
    product = SupplierProduct(
        supplier_id="DIRECT-01",
        sku="SKU-DIR-01",
        title="Branded Product",
        supplier_type=SupplierType.DIRECT,
        cost=25.0,
        shipping_cost=5.0,
        inventory_count=50,
        allows_reselling=False,
    )
    result = validate_supplier(product)
    assert result.is_valid is False
    assert "do not authorize commercial reselling" in result.reason


def test_supplier_out_of_stock():
    product = SupplierProduct(
        supplier_id="WHOLESALE-01",
        sku="SKU-OOS-01",
        title="Out of stock product",
        supplier_type=SupplierType.WHOLESALE,
        cost=10.0,
        shipping_cost=2.0,
        inventory_count=0,
        allows_reselling=True,
    )
    result = validate_supplier(product)
    assert result.is_valid is False
    assert "out of stock" in result.reason


def test_supplier_zero_lead_time_allowed():
    product = SupplierProduct(
        supplier_id="WHOLESALE-01",
        sku="SKU-SAME-DAY",
        title="Same day dispatch product",
        supplier_type=SupplierType.WHOLESALE,
        cost=10.0,
        shipping_cost=2.0,
        inventory_count=10,
        lead_time_days=0,
        allows_reselling=True,
    )
    result = validate_supplier(product)
    assert result.is_valid is True
    assert "valid_lead_time" in result.passed_checks


def test_supplier_long_lead_time_warning():
    product = SupplierProduct(
        supplier_id="WHOLESALE-01",
        sku="SKU-LONG-LEAD",
        title="Long lead time product",
        supplier_type=SupplierType.WHOLESALE,
        cost=10.0,
        shipping_cost=2.0,
        inventory_count=10,
        lead_time_days=60,
        allows_reselling=True,
    )
    result = validate_supplier(product)
    assert result.is_valid is True
    assert len(result.warnings) > 0
    assert "Extended lead time" in result.warnings[0]


def test_validate_supplier_product_helper_tuple():
    product = SupplierProduct(
        supplier_id="WHOLESALE-01",
        sku="SKU-TUPLE-1",
        title="Test Tuple Item",
        supplier_type=SupplierType.WHOLESALE,
        cost=10.0,
        shipping_cost=2.0,
        inventory_count=10,
        allows_reselling=True,
    )
    is_valid, reason = validate_supplier_product(product)
    assert is_valid is True
    assert "passed all validation checks" in reason
