from src.commerce.ebay_listing_facts_builder import extract_supplier_images


TITLE = (
    "Long Handle Floor Scrub Brush with Squeegee "
    "Hair Cleaning Comb Stiff Bristle Brush Useful Cleaning Tool"
)


def test_extract_supplier_images_keeps_only_matching_product_gallery():
    html = f"""
    <html>
      <img src="https://www.godropship.co.uk/template/front/base/resources/img/logo.png">
      <img src="https://www.godropship.co.uk/template/front/base/resources/img/whatsapp-right.png"
           alt="whatsApp-img">

      <img src="https://www.godropship.co.uk/uploadfile/images/598808/2026-08/product-1.png"
           alt="{TITLE}">
      <img src="https://www.godropship.co.uk/uploadfile/images/598808/2026-08/product-2.png"
           alt="{TITLE}">

      <img src="https://www.godropship.co.uk/uploadfile/images/598808/2026-08/thumbnail_other.png"
           alt="Another Product">
    </html>
    """

    assert extract_supplier_images(
        html,
        product_title=TITLE,
    ) == [
        "https://www.godropship.co.uk/uploadfile/images/598808/2026-08/product-1.png",
        "https://www.godropship.co.uk/uploadfile/images/598808/2026-08/product-2.png",
    ]


def test_extract_supplier_images_deduplicates_and_preserves_order():
    html = f"""
    <img src="https://www.godropship.co.uk/uploadfile/images/a.png"
         alt="{TITLE}">
    <img src="https://www.godropship.co.uk/uploadfile/images/b.png"
         alt="{TITLE}">
    <img src="https://www.godropship.co.uk/uploadfile/images/a.png"
         alt="{TITLE}">
    """

    assert extract_supplier_images(
        html,
        product_title=TITLE,
    ) == [
        "https://www.godropship.co.uk/uploadfile/images/a.png",
        "https://www.godropship.co.uk/uploadfile/images/b.png",
    ]


def test_extract_supplier_images_rejects_unrelated_recommendations():
    html = f"""
    <img src="https://www.godropship.co.uk/uploadfile/images/product.png"
         alt="{TITLE}">
    <img src="https://www.godropship.co.uk/uploadfile/products/x/other.jpg"
         alt="Completely Different Product">
    """

    assert extract_supplier_images(
        html,
        product_title=TITLE,
    ) == [
        "https://www.godropship.co.uk/uploadfile/images/product.png",
    ]
