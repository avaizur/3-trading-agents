import pytest

from src.commerce.profit_engine import (
    DEFAULT_MIN_MARGIN_PCT,
    calculate_profit,
    evaluate_profit_from_input,
)
from src.commerce.schemas import ProfitCalculationInput


def test_default_min_margin_constant():
    assert DEFAULT_MIN_MARGIN_PCT == 0.20


def test_profit_calculation_meets_20pct_margin():
    # Input: supplier cost 50, shipping 10, platform fee 10, return buffer 5, sale price 100
    # Total cost = 50 + 10 + 10 + 5 = 75
    # Net profit = 100 - 75 = 25
    # Margin = 25 / 100 = 0.25 (25%) >= 20%
    result = calculate_profit(
        supplier_cost=50.0,
        shipping=10.0,
        platform_fee=10.0,
        return_buffer=5.0,
        sale_price=100.0,
    )

    assert result.allowed is True
    assert result.meets_minimum_margin is True
    assert result.total_cost == 75.0
    assert result.net_profit == 25.0
    assert result.margin_pct == 0.25
    assert result.min_margin_pct == 0.20
    assert "Meets minimum margin requirement" in result.reason


def test_profit_calculation_below_minimum_margin():
    # Input: supplier cost 70, shipping 10, platform fee 10, return buffer 5, sale price 100
    # Total cost = 70 + 10 + 10 + 5 = 95
    # Net profit = 100 - 95 = 5
    # Margin = 5 / 100 = 0.05 (5%) < 20%
    result = calculate_profit(
        supplier_cost=70.0,
        shipping=10.0,
        platform_fee=10.0,
        return_buffer=5.0,
        sale_price=100.0,
    )

    assert result.allowed is False
    assert result.meets_minimum_margin is False
    assert result.total_cost == 95.0
    assert result.net_profit == 5.0
    assert result.margin_pct == 0.05
    assert "below minimum requirement" in result.reason


def test_profit_calculation_exact_boundary():
    # Input: total cost 80, sale price 100 -> net profit 20, margin 20% == min margin 20%
    result = calculate_profit(
        supplier_cost=60.0,
        shipping=10.0,
        platform_fee=8.0,
        return_buffer=2.0,
        sale_price=100.0,
        min_margin_pct=0.20,
    )

    assert result.allowed is True
    assert result.meets_minimum_margin is True
    assert result.total_cost == 80.0
    assert result.net_profit == 20.0
    assert result.margin_pct == 0.20


def test_profit_calculation_custom_margin():
    # Target 30% margin
    result_fail = calculate_profit(
        supplier_cost=50.0,
        shipping=10.0,
        platform_fee=10.0,
        return_buffer=5.0,
        sale_price=100.0,
        min_margin_pct=0.30,  # 25% margin fails 30% threshold
    )
    assert result_fail.allowed is False
    assert result_fail.meets_minimum_margin is False

    # Target 15% margin
    result_pass = calculate_profit(
        supplier_cost=70.0,
        shipping=5.0,
        platform_fee=5.0,
        return_buffer=2.0,
        sale_price=100.0,
        min_margin_pct=0.15,  # 18% margin passes 15% threshold
    )
    assert result_pass.allowed is True
    assert result_pass.meets_minimum_margin is True


def test_profit_calculation_percentage_input_normalization():
    # Passing 20 instead of 0.20
    result = calculate_profit(
        supplier_cost=50.0,
        shipping=10.0,
        platform_fee=10.0,
        return_buffer=5.0,
        sale_price=100.0,
        min_margin_pct=20.0,  # supplied as 20%
    )
    assert result.min_margin_pct == 0.20
    assert result.allowed is True


def test_profit_calculation_invalid_sale_price():
    result_zero = calculate_profit(
        supplier_cost=50.0,
        shipping=10.0,
        platform_fee=10.0,
        return_buffer=5.0,
        sale_price=0.0,
    )
    assert result_zero.allowed is False
    assert "sale price must be greater than zero" in result_zero.reason

    result_neg = calculate_profit(
        supplier_cost=50.0,
        shipping=10.0,
        platform_fee=10.0,
        return_buffer=5.0,
        sale_price=-10.0,
    )
    assert result_neg.allowed is False
    assert "sale price must be greater than zero" in result_neg.reason


def test_profit_calculation_negative_costs():
    result_supplier = calculate_profit(
        supplier_cost=-10.0,
        shipping=5.0,
        platform_fee=5.0,
        return_buffer=5.0,
        sale_price=100.0,
    )
    assert result_supplier.allowed is False
    assert "supplier cost must be greater than zero" in result_supplier.reason

    result_shipping = calculate_profit(
        supplier_cost=10.0,
        shipping=-5.0,
        platform_fee=5.0,
        return_buffer=5.0,
        sale_price=100.0,
    )
    assert result_shipping.allowed is False
    assert "cannot be negative" in result_shipping.reason


def test_profit_calculation_loss():
    result = calculate_profit(
        supplier_cost=90.0,
        shipping=15.0,
        platform_fee=15.0,
        return_buffer=5.0,
        sale_price=100.0,
    )
    assert result.allowed is False
    assert result.net_profit == -25.0
    assert result.margin_pct == -0.25


def test_evaluate_profit_from_input_model():
    input_model = ProfitCalculationInput(
        supplier_cost=40.0,
        shipping=8.0,
        platform_fee=6.0,
        return_buffer=2.0,
        sale_price=80.0,
        min_margin_pct=0.20,
    )
    # total cost = 56, net profit = 24, margin = 24 / 80 = 30%
    result = evaluate_profit_from_input(input_model)
    assert result.allowed is True
    assert result.net_profit == 24.0
    assert result.margin_pct == 0.30
