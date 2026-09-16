from decimal import Decimal

from src.commerce.market_research import MarketListing
from src.commerce.opportunity_scoring import (
    OpportunityDecision,
    ScoredMarketOpportunity,
)
from src.commerce.schemas import ProductLane, SupplierBackedProduct
from src.commerce.supplier_matching import match_supplier_catalog


def opportunity(title):
    listing = MarketListing(
        title=title,
        item_id="LIVE-1",
        price=Decimal("19.99"),
        currency="GBP",
        seller="seller",
        category="Pet Supplies",
        item_url="https://www.ebay.co.uk/itm/LIVE-1",
        condition="New",
        availability="IN_STOCK",
    )

    return ScoredMarketOpportunity(
        listing=listing,
        seasonal_relevance=80,
        price_attractiveness=80,
        competition_density=80,
        signal_quality=100,
        data_completeness=90,
        overall_score=80,
        decision=OpportunityDecision.SHORTLIST,
        reasons=(),
    )


def product(sku, name):
    return SupplierBackedProduct(
        supplier_name="Go Dropship",
        supplier_sku=sku,
        product_name=name,
        supplier_cost=10.0,
        lane=ProductLane.EVERGREEN,
    )


def test_matches_meaningfully_similar_supplier_product():
    products = [
        product("PET-73719", "large soft pet carrier"),
        product("PET-73135", "anti-splash cat litter box"),
    ]

    matches = match_supplier_catalog(
        opportunity("Soft Pet Carrier Travel Bag for Cats and Dogs"),
        products,
    )

    assert len(matches) == 1
    assert matches[0].supplier_sku == "PET-73719"
    assert "carrier" in matches[0].shared_terms
    assert "pet" in matches[0].shared_terms


def test_generic_decoration_word_does_not_create_false_match():
    products = [
        product("HOM-55216", "6pc Christmas feather ornaments"),
    ]

    matches = match_supplier_catalog(
        opportunity("Halloween Pumpkin Party Decorations"),
        products,
    )

    assert matches == []
