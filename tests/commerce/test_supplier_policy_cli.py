from src.commerce.database import CommerceDatabase
from src.commerce.supplier_policy_cli import main


def test_supplier_policy_cli_persists_rules(tmp_path):
    db_path = tmp_path / "commerce.db"

    result = main([
        "TEST-SUPPLIER",
        "--dispatch-time-days", "3",
        "--shipping-service", "UK_RoyalMailSecondClassStandard",
        "--remote-surcharge", "0",
        "--blind-ship", "yes",
        "--return-route", "SUPPLIER",
        "--rma-required", "yes",
        "--return-postage", "BUYER",
        "--supplier-fault-resolution", "REFUND_OR_REPLACE_AFTER_EVIDENCE",
        "--db", str(db_path),
    ])

    assert result == 0

    rules = CommerceDatabase(str(db_path)).get_supplier_policy_rules("TEST-SUPPLIER")

    assert rules is not None
    assert rules.dispatch_time_days == 3
    assert rules.shipping_services == ["UK_RoyalMailSecondClassStandard"]
    assert rules.blind_ship is True
    assert rules.return_route.value == "SUPPLIER"
    assert rules.rma_required is True
    assert rules.return_postage.value == "BUYER"
    assert (
        rules.supplier_fault_resolution
        == "REFUND_OR_REPLACE_AFTER_EVIDENCE"
    )
