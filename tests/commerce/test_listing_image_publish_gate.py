import pytest

from src.commerce.ebay_inventory_service import (
    validate_listing_facts,
)


def valid_facts():
    return {
        "ebay_title": "Test Product",
        "ebay_category_id": "12345",
        "image_urls": [
            "https://www.godropship.co.uk/uploadfile/images/product.png"
        ],
        "condition": "NEW",
        "aspects": {"Brand": ["Unbranded"]},
    }


def test_accepts_product_image():
    validate_listing_facts(valid_facts())


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://www.godropship.co.uk/template/front/base/resources/img/logo.png",
        "https://www.godropship.co.uk/template/front/base/resources/img/usa.png",
        "https://www.godropship.co.uk/template/front/base/resources/img/whatsapp-right.png",
        "https://www.godropship.co.uk/uploadfile/images/thumbnail_product.png",
    ],
)
def test_rejects_invalid_image(bad_url):
    facts = valid_facts()
    facts["image_urls"].append(bad_url)

    with pytest.raises(ValueError, match="Invalid supplier image"):
        validate_listing_facts(facts)
