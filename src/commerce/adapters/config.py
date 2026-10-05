from dataclasses import dataclass
from typing import Optional

from src.commerce.schemas import Platform


@dataclass(frozen=True)
class SupplierConfig:
    name: str
    adapter_key: str
    enabled: bool = True
    secret_name: Optional[str] = None


@dataclass(frozen=True)
class MarketplaceConfig:
    platform: Platform
    adapter_key: str
    enabled: bool = False
    secret_name: Optional[str] = None
    min_margin_pct: float = 20.0
    human_approval_required: bool = True


SUPPLIERS = {
    "go_dropship": SupplierConfig(
        name="Go Dropship",
        adapter_key="go_dropship",
        enabled=True,
    ),
}


MARKETPLACES = {
    Platform.EBAY: MarketplaceConfig(
        platform=Platform.EBAY,
        adapter_key="ebay",
        enabled=True,
        secret_name="3-trading-agents/ebay-production",
    ),
    Platform.TIKTOK_SHOP: MarketplaceConfig(
        platform=Platform.TIKTOK_SHOP,
        adapter_key="tiktok_shop",
        enabled=False,
    ),
    Platform.AMAZON: MarketplaceConfig(
        platform=Platform.AMAZON,
        adapter_key="amazon",
        enabled=False,
    ),
    Platform.ETSY: MarketplaceConfig(
        platform=Platform.ETSY,
        adapter_key="etsy",
        enabled=False,
    ),
}
