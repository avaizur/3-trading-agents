import sqlite3

from src.commerce.database import CommerceDatabase
from src.commerce.ebay_policy_discovery import EBaySellerPolicyDiscovery
from src.commerce.policy_compatibility import match_supplier_to_ebay_policies
from src.commerce.schemas import (
    PolicyCompatibilityStatus, ReturnPostagePayer, ReturnRoute, SupplierPolicyRules,
)


def _transport(calls):
    def get(url, headers, timeout):
        calls.append((url, headers, timeout))
        if "fulfillment_policy" in url:
            return {"fulfillmentPolicies": [{
                "fulfillmentPolicyId": "F1", "name": "Supplier delivery", "marketplaceId": "EBAY_GB",
                "handlingTime": {"value": 3, "unit": "DAY"},
                "shippingOptions": [{"shippingServices": [{"shippingServiceCode": "UK_RoyalMail48"}]}],
                "shipToLocations": {"regionExcluded": [{"regionName": "Channel Islands"}]},
            }]}
        if "return_policy" in url:
            return {"returnPolicies": [{"returnPolicyId": "R1", "name": "Returns", "marketplaceId": "EBAY_GB",
                                        "returnsAccepted": True, "returnPeriod": {"value": 30, "unit": "DAY"},
                                        "returnShippingCostPayer": "BUYER"}]}
        if "payment_policy" in url:
            return {"paymentPolicies": [{"paymentPolicyId": "P1", "name": "Managed", "marketplaceId": "EBAY_GB"}]}
        return {"locations": [{"merchantLocationKey": "L1", "name": "Warehouse",
                               "locationTypes": ["WAREHOUSE"], "merchantLocationStatus": "ENABLED"}], "total": 1}
    return get


def _rules(**updates):
    values = dict(supplier_id="SUP-1", dispatch_time_days=2,
                  shipping_services=["UK_RoyalMail48"], remote_surcharge=4.5,
                  blind_ship=True, return_route=ReturnRoute.SUPPLIER,
                  rma_required=True, return_postage=ReturnPostagePayer.BUYER)
    values.update(updates)
    return SupplierPolicyRules(**values)


def test_discovery_is_get_only_normalized_and_token_is_not_in_result():
    calls = []
    snapshot = EBaySellerPolicyDiscovery("top-secret", transport=_transport(calls)).discover()
    assert len(calls) == 4
    assert all(call[1]["Authorization"] == "Bearer top-secret" for call in calls)
    assert "top-secret" not in snapshot.model_dump_json()
    assert snapshot.fulfillment_policies[0].shipping_services == ["UK_RoyalMail48"]
    assert snapshot.inventory_locations[0].merchant_location_key == "L1"


def test_persist_and_match_only_normalized_settings(tmp_path):
    db = CommerceDatabase(str(tmp_path / "policies.db"))
    saved = db.save_supplier_policy_rules(_rules())
    snapshot = EBaySellerPolicyDiscovery("secret", transport=_transport([])).discover()
    db.save_ebay_policy_snapshot(snapshot)
    result = match_supplier_to_ebay_policies(saved, db.get_ebay_policy_snapshot("EBAY_GB"))
    assert result.status is PolicyCompatibilityStatus.MATCHED
    assert (result.fulfillment_policy_id, result.return_policy_id,
            result.payment_policy_id, result.inventory_location_key) == ("F1", "R1", "P1", "L1")
    with sqlite3.connect(tmp_path / "policies.db") as conn:
        stored = " ".join(str(value) for row in conn.execute("SELECT * FROM ebay_policy_snapshots") for value in row)
    assert "secret" not in stored
    assert "Authorization" not in stored


def test_mismatch_has_reason_and_no_selected_ids():
    snapshot = EBaySellerPolicyDiscovery("secret", transport=_transport([])).discover()
    result = match_supplier_to_ebay_policies(_rules(blind_ship=False, dispatch_time_days=5), snapshot)
    assert result.status is PolicyCompatibilityStatus.MISMATCH
    assert "blind shipping" in result.reason
    assert "dispatch time" in result.reason
    assert result.fulfillment_policy_id is None
