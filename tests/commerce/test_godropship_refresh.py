from src.commerce.godropship_discovery import parse_product_snapshot


def test_product_snapshot_keeps_low_stock_and_changed_cost():
    html = """
    <html>
      <body>
        <h1>Example Product</h1>
        <p>Item Code: SKU-123</p>
        <p>UK Stock: 5</p>
        <p>Price: £18.75</p>
      </body>
    </html>
    """

    result = parse_product_snapshot(
        "https://www.godropship.co.uk/example",
        html,
    )

    assert result is not None
    assert result.sku == "SKU-123"
    assert result.stock == 5
    assert result.cost == 18.75
