from src.commerce.adapters.amazon import AmazonAdapter
from src.commerce.adapters.ebay import EBayAdapter
from src.commerce.adapters.etsy import EtsyAdapter
from src.commerce.adapters.godropship import GoDropshipAdapter
from src.commerce.adapters.tiktok_shop import TikTokShopAdapter
from src.commerce.schemas import Platform


MARKETPLACE_ADAPTERS = {
    Platform.EBAY: EBayAdapter,
    Platform.TIKTOK_SHOP: TikTokShopAdapter,
    Platform.AMAZON: AmazonAdapter,
    Platform.ETSY: EtsyAdapter,
}


def get_marketplace_adapter(platform: Platform | str):
    if isinstance(platform, str):
        platform = Platform(platform.upper())

    adapter_class = MARKETPLACE_ADAPTERS.get(platform)

    if adapter_class is None:
        raise KeyError(
            f"No marketplace adapter registered for {platform!s}"
        )

    return adapter_class()


def get_supplier_adapter(
    supplier_name: str,
    *,
    store=None,
):
    normalized = supplier_name.strip().casefold()

    if normalized in {
        "go dropship",
        "godropship",
        "go_dropship",
    }:
        return GoDropshipAdapter(store=store)

    raise KeyError(
        f"No supplier adapter registered for {supplier_name!r}"
    )
