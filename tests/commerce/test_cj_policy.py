from src.commerce.cj_policy import CJ_RETURN_RESERVE_RATE, cj_supplier_policy
from src.commerce.schemas import ReturnPostagePayer, ReturnRoute


def test_cj_policy_is_restricted_seller_managed():
    rules = cj_supplier_policy()

    assert rules.supplier_id == "cjdropshipping"
    assert rules.blind_ship is True
    assert rules.return_route == ReturnRoute.SELLER
    assert rules.return_postage == ReturnPostagePayer.SELLER
    assert rules.rma_required is True
    assert CJ_RETURN_RESERVE_RATE == 0.15
