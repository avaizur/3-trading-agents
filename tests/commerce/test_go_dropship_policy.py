from src.commerce.database import CommerceDatabase
from src.commerce.schemas import (
    ReturnPostagePayer,
    ReturnRoute,
    SupplierPolicyRules,
)


def test_go_dropship_policy_can_record_fault_resolution(tmp_path):
    rules = SupplierPolicyRules(
        supplier_id="go_dropship",
        dispatch_time_days=2,
        shipping_services=["TRACKED_2_BUSINESS_DAY"],
        remote_surcharge=0.0,
        blind_ship=True,
        return_route=ReturnRoute.SUPPLIER,
        rma_required=True,
        return_postage=ReturnPostagePayer.BUYER,
        supplier_fault_resolution="REFUND_OR_REPLACE_AFTER_EVIDENCE",
    )

    db = CommerceDatabase(str(tmp_path / "commerce.db"))
    saved = db.save_supplier_policy_rules(rules)
    loaded = db.get_supplier_policy_rules("go_dropship")

    assert saved.supplier_fault_resolution == "REFUND_OR_REPLACE_AFTER_EVIDENCE"
    assert loaded is not None
    assert loaded.return_postage is ReturnPostagePayer.BUYER
    assert loaded.supplier_fault_resolution == "REFUND_OR_REPLACE_AFTER_EVIDENCE"


def test_go_dropship_policy_defaults_fault_resolution_to_none():
    rules = SupplierPolicyRules(
        supplier_id="other_supplier",
        dispatch_time_days=3,
        shipping_services=["STANDARD"],
        remote_surcharge=0.0,
        blind_ship=True,
        return_route=ReturnRoute.SUPPLIER,
        rma_required=True,
        return_postage=ReturnPostagePayer.BUYER,
    )

    assert rules.supplier_fault_resolution is None
