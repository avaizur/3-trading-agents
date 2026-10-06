import importlib.util
from pathlib import Path


HANDLER_PATH = (
    Path(__file__).parents[2]
    / "src"
    / "lambda"
    / "commerce_daily_summary"
    / "handler.py"
)

spec = importlib.util.spec_from_file_location("commerce_daily_summary_handler", HANDLER_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_summary_contains_only_actionable_approval_link():
    event = {
        "discovery": {
            "Payload": {
                "discovered": 20,
                "imported": 16,
            }
        },
        "watch": {
            "watch": {
                "watch_counts": {
                    "PASS": 33,
                    "REJECT": 2,
                    "NEEDS_REFRESH": 1,
                },
                "pipeline_counts": {
                    "READY_FOR_HUMAN_REVIEW": 16,
                    "REVIEW": 12,
                    "ALREADY_LIVE": 5,
                },
                "decisions": [
                    {
                        "supplier_sku": "HOM-76522",
                        "product_name": "Christmas Gift Bags",
                        "market_price": 8.35,
                        "expected_profit": 3.24,
                        "expected_margin": 0.388,
                        "pipeline": {
                            "approval_request_created": True,
                            "approval_url": "https://example.test/review?token=abc",
                        },
                    },
                    {
                        "supplier_sku": "NO-LINK",
                        "product_name": "Not Ready",
                        "pipeline": {
                            "approval_request_created": False,
                            "approval_error": "Verified facts not ready.",
                        },
                    },
                ],
            }
        },
        "replenishment": {
            "replenishment": {
                "checked": 2,
                "results": [
                    {
                        "sku": "LIVE-1",
                        "status": "IN_STOCK",
                    },
                    {
                        "sku": "GEM-76624",
                        "status": "BLOCKED",
                        "reason": "Fresh supplier check failed: ValueError",
                    },
                ],
            }
        },
    }

    result = module.lambda_handler(event, None)

    assert result["subject"] == "3 Trading Agents - 1 approval waiting"
    assert "HOM-76522 - Christmas Gift Bags" in result["message"]
    assert "https://example.test/review?token=abc" in result["message"]
    assert "NO-LINK" not in result["message"]
    assert "Market price: £8.35" in result["message"]
    assert "Expected profit: £3.24" in result["message"]
    assert "Margin: 38.8%" in result["message"]
    assert "GEM-76624: WARNING - BLOCKED" in result["message"]
    assert "No automatic supplier orders were placed." in result["message"]


def test_summary_handles_no_approvals():
    event = {
        "discovery": {"Payload": {}},
        "watch": {
            "watch": {
                "watch_counts": {},
                "pipeline_counts": {},
                "decisions": [],
            }
        },
        "replenishment": {
            "replenishment": {
                "checked": 0,
                "results": [],
            }
        },
    }

    result = module.lambda_handler(event, None)

    assert result["subject"] == "3 Trading Agents - 0 approvals waiting"
    assert "No new approval links require action today." in result["message"]
