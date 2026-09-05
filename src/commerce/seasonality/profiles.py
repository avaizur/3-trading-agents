"""Product search profiles.

Edit the values in ``DEFAULT_SEARCH_PROFILES`` to tune Product Scout guidance.
These are search hints only; no supplier or marketplace calls are made here.
"""

from .models import ProductSearchProfile


DEFAULT_SEARCH_PROFILES: dict[str, ProductSearchProfile] = {
    "halloween": ProductSearchProfile(
        event_key="halloween",
        categories=("Costumes", "Party Decorations", "Home & Garden"),
        keywords=("halloween costume", "spooky decorations", "pumpkin decor"),
        exclusions=("used", "damaged", "digital download", "adult only"),
        priority_score=90,
    ),
    "bonfire-night": ProductSearchProfile(
        event_key="bonfire-night",
        categories=("Outdoor Heating", "Outdoor Lighting", "Winter Accessories"),
        keywords=("bonfire night", "fire pit accessories", "outdoor string lights"),
        exclusions=("fireworks", "explosives", "used", "damaged"),
        priority_score=70,
    ),
    "black-friday": ProductSearchProfile(
        event_key="black-friday",
        categories=("Consumer Electronics", "Home Appliances", "Toys & Games"),
        keywords=("black friday deal", "gift bundle", "best seller"),
        exclusions=("used", "refurbished", "damaged", "parts only"),
        priority_score=100,
    ),
    "cyber-monday": ProductSearchProfile(
        event_key="cyber-monday",
        categories=("Computing Accessories", "Smart Home", "Gaming Accessories"),
        keywords=("cyber monday deal", "tech gift", "home office accessory"),
        exclusions=("used", "refurbished", "damaged", "subscription"),
        priority_score=95,
    ),
    "christmas": ProductSearchProfile(
        event_key="christmas",
        categories=("Gifts", "Toys & Games", "Christmas Decorations"),
        keywords=("christmas gift", "stocking filler", "festive decoration"),
        exclusions=("used", "damaged", "personalised", "pre-order"),
        priority_score=100,
    ),
    "new-year": ProductSearchProfile(
        event_key="new-year",
        categories=("Party Supplies", "Fitness", "Home Organisation"),
        keywords=("new year party", "fitness resolution", "home organiser"),
        exclusions=("used", "damaged", "digital download", "alcohol"),
        priority_score=80,
    ),
}


def get_search_profile(event_key: str) -> ProductSearchProfile | None:
    """Return the configured profile for an event, if one exists."""
    return DEFAULT_SEARCH_PROFILES.get(event_key)
