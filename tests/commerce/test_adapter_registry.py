import pytest

from src.commerce.adapters import (
    AmazonAdapter,
    EBayAdapter,
    EtsyAdapter,
    GoDropshipAdapter,
    PlatformDisabledError,
    TikTokShopAdapter,
    get_marketplace_adapter,
    get_supplier_adapter,
)
from src.commerce.schemas import Platform


def test_marketplace_registry_contains_all_supported_platforms():
    assert isinstance(
        get_marketplace_adapter(Platform.EBAY),
        EBayAdapter,
    )
    assert isinstance(
        get_marketplace_adapter(Platform.TIKTOK_SHOP),
        TikTokShopAdapter,
    )
    assert isinstance(
        get_marketplace_adapter(Platform.AMAZON),
        AmazonAdapter,
    )
    assert isinstance(
        get_marketplace_adapter(Platform.ETSY),
        EtsyAdapter,
    )


def test_marketplace_registry_accepts_strings():
    adapter = get_marketplace_adapter("TIKTOK_SHOP")
    assert adapter.platform == Platform.TIKTOK_SHOP


@pytest.mark.parametrize(
    "platform",
    [
        Platform.TIKTOK_SHOP,
        Platform.AMAZON,
        Platform.ETSY,
    ],
)
def test_future_marketplaces_are_safe_by_default(platform):
    adapter = get_marketplace_adapter(platform)

    assert adapter.is_enabled is False

    with pytest.raises(PlatformDisabledError):
        adapter.estimate_fees(20.0)


def test_go_dropship_supplier_registry():
    adapter = get_supplier_adapter("Go Dropship")

    assert isinstance(adapter, GoDropshipAdapter)
    assert adapter.supplier_name == "Go Dropship"

    status = adapter.test_connection()

    assert status["supports_discovery"] is True
    assert status["automated_ordering"] is False


def test_unknown_supplier_is_rejected():
    with pytest.raises(KeyError):
        get_supplier_adapter("Unknown Warehouse")
