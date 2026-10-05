from src.commerce.adapters.config import MARKETPLACES, SUPPLIERS
from src.commerce.schemas import Platform


def test_go_dropship_is_active_supplier():
    cfg = SUPPLIERS["go_dropship"]

    assert cfg.enabled is True
    assert cfg.name == "Go Dropship"


def test_ebay_is_enabled_marketplace():
    cfg = MARKETPLACES[Platform.EBAY]

    assert cfg.enabled is True
    assert cfg.min_margin_pct == 20.0
    assert cfg.human_approval_required is True


def test_future_marketplaces_are_disabled_by_default():
    assert MARKETPLACES[Platform.TIKTOK_SHOP].enabled is False
    assert MARKETPLACES[Platform.AMAZON].enabled is False
    assert MARKETPLACES[Platform.ETSY].enabled is False
