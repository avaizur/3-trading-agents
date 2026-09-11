import pytest

from src.commerce.higher_ticket_scoring import (
    HigherTicketDecision,
    HigherTicketEconomics,
    score_higher_ticket_ebay_product,
)


def economics(**overrides):
    values = dict(
        sale_price=60,
        supplier_cost=30,
        supplier_basket_total=30,
        supplier_basket_minimum=20,
        handling_cost=2,
        delivery_cost=4,
        platform_fees=7,
        return_allowance=3,
    )
    values.update(overrides)
    return HigherTicketEconomics(**values)


def test_eligible_product_accounts_for_all_costs_and_only_recommends_review():
    result = score_higher_ticket_ebay_product(
        economics(), supplier_name="Acme Wholesale", return_risk_score=50
    )

    assert result.decision is HigherTicketDecision.REVIEW
    assert result.total_cost == 46
    assert result.expected_profit == 14
    assert result.margin_pct == pytest.approx(0.2333)
    assert result.human_review_required is True
    assert result.auto_approved is False
    assert result.publish_allowed is False


@pytest.mark.parametrize("sale_price", [34.99, 80.01])
def test_sale_price_must_be_in_higher_ticket_range(sale_price):
    result = score_higher_ticket_ebay_product(
        economics(sale_price=sale_price),
        supplier_name="Acme Wholesale",
        return_risk_score=85,
    )
    assert result.decision is HigherTicketDecision.REJECT
    assert any("between £35 and £80" in reason for reason in result.reasons)


def test_profit_and_margin_are_independent_gates():
    low_profit = score_higher_ticket_ebay_product(
        economics(sale_price=35, supplier_cost=20, platform_fees=4,
                  delivery_cost=2, handling_cost=1, return_allowance=2),
        supplier_name="Acme Wholesale",
        return_risk_score=85,
    )
    low_margin = score_higher_ticket_ebay_product(
        economics(sale_price=40, supplier_cost=26, platform_fees=4,
                  delivery_cost=2, handling_cost=1, return_allowance=0),
        supplier_name="Acme Wholesale",
        return_risk_score=85,
    )

    assert low_profit.expected_profit == 6
    assert any("at least £7" in reason for reason in low_profit.reasons)
    assert low_margin.expected_profit == 7
    assert low_margin.margin_pct == 0.175
    assert any("at least 20%" in reason for reason in low_margin.reasons)


def test_supplier_basket_and_wicked_nights_minimum_are_enforced():
    general = score_higher_ticket_ebay_product(
        economics(supplier_basket_total=19),
        supplier_name="Acme Wholesale",
        return_risk_score=85,
    )
    wicked = score_higher_ticket_ebay_product(
        economics(supplier_basket_total=24, supplier_basket_minimum=0),
        supplier_name="Wicked Nights",
        return_risk_score=85,
    )

    assert any("supplier basket minimum" in reason for reason in general.reasons)
    assert any("at least £25" in reason for reason in wicked.reasons)


def test_high_return_risk_is_rejected_but_medium_is_eligible():
    high_risk = score_higher_ticket_ebay_product(
        economics(), supplier_name="Acme", return_risk_score=49
    )
    medium_risk = score_higher_ticket_ebay_product(
        economics(), supplier_name="Acme", return_risk_score=50
    )

    assert high_risk.decision is HigherTicketDecision.REJECT
    assert medium_risk.decision is HigherTicketDecision.REVIEW
