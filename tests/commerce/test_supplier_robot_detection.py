from src.commerce.godropship_discovery import is_robot_verification_page


def test_detects_godropship_robot_verification():
    html = '<form id="VERYFICATIONROBOTFORM" method="post"></form>'
    assert is_robot_verification_page(html)


def test_allows_normal_product_page():
    html = '<html><img src="/uploadfile/product.png"></html>'
    assert not is_robot_verification_page(html)
