from src.commerce.godropship_discovery import _parse_product_page
from src.commerce.schemas import ProductLane


def test_parse_safe_product():
    html = """
    <html>
      <h1>3pcs Radiator Cleaner Brush 78cm Flexible Long Duster</h1>
      <div>
        Item Code : HOM-TEST01
        Weight : 300.00 g
        UK Stock : 99
        Price : £5.74
      </div>
    </html>
    """

    product = _parse_product_page(
        "https://www.godropship.co.uk/test-product",
        html,
    )

    assert product is not None
    assert product.sku == "HOM-TEST01"
    assert product.cost == 5.74
    assert product.stock == 99
    assert product.lane is ProductLane.EVERGREEN


def test_reject_low_stock():
    html = """
    <html>
      <h1>Simple Kitchen Storage Product</h1>
      <div>
        Item Code : HOM-TEST02
        UK Stock : 10
        Price : £6.50
      </div>
    </html>
    """

    assert _parse_product_page(
        "https://www.godropship.co.uk/test",
        html,
    ) is None


def test_reject_risky_product():
    html = """
    <html>
      <h1>Reusable Medical Incontinence Bed Pad</h1>
      <div>
        Item Code : MED-TEST01
        UK Stock : 100
        Price : £7.16
      </div>
    </html>
    """

    assert _parse_product_page(
        "https://www.godropship.co.uk/test",
        html,
    ) is None


def test_seasonal_classification():
    html = """
    <html>
      <h1>Christmas Decorative Storage Ornament</h1>
      <div>
        Item Code : XMS-TEST01
        UK Stock : 100
        Price : £7.00
      </div>
    </html>
    """

    product = _parse_product_page(
        "https://www.godropship.co.uk/test",
        html,
    )

    assert product is not None
    assert product.lane is ProductLane.SEASONAL
