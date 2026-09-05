from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.commerce.database import CommerceDatabase
from src.commerce.market_research import MarketListing
from src.commerce.opportunity_scoring import OpportunityDecision, ScoredMarketOpportunity
from src.commerce.schemas import CandidateStatus, SupplierProfitStatus
from src.commerce.supplier_matching import (
    ManualSupplierInput,
    ManualSupplierMatcher,
    SupplierMatchInterface,
)


def opportunity(decision=OpportunityDecision.SHORTLIST):
    listing = MarketListing(
        title="Manual supplier match item", item_id="12345",
        price=Decimal("100.00"), currency="GBP", seller="market_seller",
        category="Home", item_url="https://www.ebay.co.uk/itm/12345",
        condition="New", availability="IN_STOCK",
        end_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    return ScoredMarketOpportunity(
        listing=listing, seasonal_relevance=90, price_attractiveness=80,
        competition_density=80, signal_quality=100, data_completeness=100,
        overall_score=88, decision=decision, reasons=(),
    )


def supplier(**overrides):
    values = {
        "name": "Acme Wholesale", "sku": "ACME-42", "cost": 50.0,
        "shipping": 5.0, "stock": 12, "direct_ship": True,
        "verification_status": "VERIFIED",
    }
    values.update(overrides)
    return ManualSupplierInput(**values)


def test_manual_match_implements_interface_and_returns_profitable():
    matcher: SupplierMatchInterface = ManualSupplierMatcher()
    result = matcher.verify(
        opportunity(), supplier(), platform_fee=10.0, return_buffer=5.0
    )
    assert result.status is SupplierProfitStatus.VERIFIED_PROFITABLE
    assert result.supplier_validation.is_valid is True
    assert result.profit_decision.net_profit == 30.0
    assert result.candidate.status is CandidateStatus.VERIFIED
    assert result.candidate.supplier_profit_status is result.status
    assert result.candidate.sku == "ACME-42"


def test_verified_supplier_below_margin_returns_low_margin():
    result = ManualSupplierMatcher().verify(
        opportunity(), supplier(cost=75.0), platform_fee=5.0, return_buffer=5.0
    )
    assert result.status is SupplierProfitStatus.VERIFIED_LOW_MARGIN
    assert result.profit_decision.allowed is False
    assert result.candidate.status is CandidateStatus.NEW


def test_supplier_profit_gate_persists_with_candidate(tmp_path):
    result = ManualSupplierMatcher().verify(opportunity(), supplier())
    db = CommerceDatabase(str(tmp_path / "supplier-match.db"))
    saved = db.save_candidate(result.candidate)

    assert saved.supplier_profit_status is SupplierProfitStatus.VERIFIED_PROFITABLE


@pytest.mark.parametrize(
    "manual_input",
    [
        ManualSupplierInput(name="Acme", verification_status="PENDING"),
        ManualSupplierInput(
            name="Acme", sku="SKU", cost=10, shipping=0, stock=1,
            direct_ship=True, verification_status="PENDING",
        ),
    ],
)
def test_incomplete_or_unverified_input_needs_supplier_data(manual_input):
    result = ManualSupplierMatcher().verify(opportunity(), manual_input)
    assert result.status is SupplierProfitStatus.NEEDS_SUPPLIER_DATA
    assert result.candidate is None
    assert result.profit_decision is None


def test_manual_rejection_and_existing_validator_rejection():
    rejected = ManualSupplierMatcher().verify(
        opportunity(), ManualSupplierInput(verification_status="REJECTED")
    )
    assert rejected.status is SupplierProfitStatus.SUPPLIER_REJECTED

    retail = ManualSupplierMatcher().verify(opportunity(), supplier(name="Amazon Prime"))
    assert retail.status is SupplierProfitStatus.SUPPLIER_REJECTED
    assert retail.supplier_validation.retail_dropshipping_blocked is True
    assert retail.profit_decision is None


def test_only_shortlisted_opportunities_are_accepted():
    with pytest.raises(ValueError, match="SHORTLIST"):
        ManualSupplierMatcher().verify(
            opportunity(OpportunityDecision.WATCH), supplier()
        )
