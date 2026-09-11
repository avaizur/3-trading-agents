import pytest

from src.commerce.higher_ticket_cli import main, score_candidate
from src.commerce.higher_ticket_scoring import HigherTicketDecision


def cli_args(**overrides):
    values = {
        "sale-price": "60",
        "supplier-name": "Acme Wholesale",
        "supplier-basket-total": "30",
        "handling": "2",
        "delivery": "4",
        "platform-fees": "7",
        "return-allowance": "3",
        "return-risk": "medium",
    }
    values.update({key.replace("_", "-"): str(value) for key, value in overrides.items()})
    return [part for key, value in values.items() for part in (f"--{key}", value)]


def test_cli_prints_pass_profit_margin_and_no_rejections(capsys):
    assert main(cli_args()) == 0

    assert capsys.readouterr().out.splitlines() == [
        "Result: PASS",
        "Expected profit: £14.00",
        "Margin: 23.33%",
        "Rejection reasons:",
        "- None",
    ]


def test_cli_prints_reject_and_all_lane_reasons(capsys):
    assert main(cli_args(
        sale_price=34,
        supplier_name="Wicked Nights",
        supplier_basket_total=24,
        handling=2,
        delivery=3,
        platform_fees=4,
        return_allowance=1,
        return_risk="high",
    )) == 0

    output = capsys.readouterr().out
    assert "Result: REJECT" in output
    assert "Expected profit: £0.00" in output
    assert "Margin: 0.00%" in output
    assert "Sale price must be between £35 and £80." in output
    assert "Wicked Nights requires a supplier basket of at least £25." in output
    assert "Expected profit must be at least £7." in output
    assert "Expected margin must be at least 20%." in output
    assert "High return-risk products are not eligible for this lane." in output


def test_score_candidate_reuses_basket_as_cost_and_accepts_low_risk():
    result = score_candidate(
        sale_price=50,
        supplier_name="Acme",
        supplier_basket_total=25,
        handling=2,
        delivery=3,
        platform_fees=5,
        return_allowance=2,
        return_risk_level="low",
    )

    assert result.decision is HigherTicketDecision.REVIEW
    assert result.total_cost == 37
    assert result.expected_profit == 13
    assert result.margin_pct == pytest.approx(0.26)


def test_invalid_return_risk_level_is_rejected():
    with pytest.raises(ValueError, match="LOW, MEDIUM, or HIGH"):
        score_candidate(
            sale_price=50,
            supplier_name="Acme",
            supplier_basket_total=25,
            handling=0,
            delivery=0,
            platform_fees=0,
            return_allowance=0,
            return_risk_level="unknown",
        )
