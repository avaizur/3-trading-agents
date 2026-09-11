"""Read-only discovery of existing eBay seller policies and inventory locations."""

import json
import os
from collections.abc import Callable
from datetime import timedelta
from math import ceil
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.commerce.schemas import (
    EBayFulfillmentPolicy,
    EBayInventoryLocation,
    EBayPaymentPolicy,
    EBayPolicySnapshot,
    EBayReturnPolicy,
    ReturnPostagePayer,
)

JsonTransport = Callable[[str, dict[str, str], float], dict[str, Any]]


def _get_json(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed eBay hosts
        return json.loads(response.read().decode("utf-8"))


class EBaySellerPolicyDiscovery:
    """GET-only eBay Account and Inventory API client.

    The credential remains private and neither headers nor raw API responses are
    exposed by the public result.
    """

    ACCOUNT_BASE_URL = "https://api.ebay.com/sell/account/v1"
    INVENTORY_BASE_URL = "https://api.ebay.com/sell/inventory/v1"

    def __init__(self, access_token: str | None = None, *, transport: JsonTransport | None = None,
                 timeout: float = 10.0):
        token = access_token or os.environ.get("EBAY_ACCESS_TOKEN")
        if not token:
            raise RuntimeError("EBAY_ACCESS_TOKEN environment variable is required")
        self.__access_token = token
        self._transport = transport or _get_json
        self.timeout = timeout

    def discover(self, marketplace_id: str = "EBAY_GB") -> EBayPolicySnapshot:
        return EBayPolicySnapshot(
            marketplace_id=marketplace_id,
            fulfillment_policies=self.get_fulfillment_policies(marketplace_id),
            return_policies=self.get_return_policies(marketplace_id),
            payment_policies=self.get_payment_policies(marketplace_id),
            inventory_locations=self.get_inventory_locations(),
        )

    def get_fulfillment_policies(self, marketplace_id: str) -> list[EBayFulfillmentPolicy]:
        return [self._fulfillment(p) for p in self._all_account(
            "fulfillment_policy", "fulfillmentPolicies", marketplace_id)]

    def get_return_policies(self, marketplace_id: str) -> list[EBayReturnPolicy]:
        return [self._returns(p) for p in self._all_account(
            "return_policy", "returnPolicies", marketplace_id)]

    def get_payment_policies(self, marketplace_id: str) -> list[EBayPaymentPolicy]:
        return [self._payment(p) for p in self._all_account(
            "payment_policy", "paymentPolicies", marketplace_id)]

    def get_inventory_locations(self) -> list[EBayInventoryLocation]:
        return [self._location(p) for p in self._all_locations()]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.__access_token}", "Accept": "application/json"}

    def _all_account(self, endpoint: str, key: str, marketplace_id: str) -> list[dict]:
        url = f"{self.ACCOUNT_BASE_URL}/{endpoint}?{urlencode({'marketplace_id': marketplace_id})}"
        results: list[dict] = []
        while url:
            payload = self._transport(url, self._headers(), self.timeout)
            results.extend(payload.get(key, []))
            url = payload.get("next") or payload.get("nextHref")
        return results

    def _all_locations(self) -> list[dict]:
        results: list[dict] = []
        offset, limit = 0, 100
        while True:
            url = f"{self.INVENTORY_BASE_URL}/location?{urlencode({'limit': limit, 'offset': offset})}"
            payload = self._transport(url, self._headers(), self.timeout)
            page = payload.get("locations", [])
            results.extend(page)
            total = int(payload.get("total", len(results)))
            if not page or len(results) >= total:
                return results
            offset += len(page)

    @staticmethod
    def _days(duration: dict | None) -> int:
        if not duration:
            return 0
        value = int(duration.get("value", 0))
        unit = str(duration.get("unit", "DAY")).upper()
        factors = {"DAY": 1, "HOUR": 1 / 24, "MINUTE": 1 / 1440}
        return ceil(timedelta(days=value * factors.get(unit, 1)).total_seconds() / 86400)

    @classmethod
    def _fulfillment(cls, raw: dict) -> EBayFulfillmentPolicy:
        services, excluded = [], []
        for option in raw.get("shippingOptions") or []:
            for service in option.get("shippingServices") or []:
                if service.get("shippingServiceCode"):
                    services.append(service["shippingServiceCode"])
        for region in (raw.get("shipToLocations") or {}).get("regionExcluded") or []:
            value = region.get("regionName") or region.get("regionType")
            if value:
                excluded.append(value)
        return EBayFulfillmentPolicy(
            policy_id=raw["fulfillmentPolicyId"], name=raw["name"],
            marketplace_id=raw.get("marketplaceId", ""),
            handling_time_days=cls._days(raw.get("handlingTime")),
            shipping_services=sorted(set(services)), excluded_regions=sorted(set(excluded)),
        )

    @classmethod
    def _returns(cls, raw: dict) -> EBayReturnPolicy:
        payer = raw.get("returnShippingCostPayer")
        return EBayReturnPolicy(
            policy_id=raw["returnPolicyId"], name=raw["name"],
            marketplace_id=raw.get("marketplaceId", ""),
            returns_accepted=bool(raw.get("returnsAccepted")),
            return_period_days=cls._days(raw.get("returnPeriod")) if raw.get("returnPeriod") else None,
            return_shipping_cost_payer=ReturnPostagePayer(payer) if payer in {"BUYER", "SELLER"} else None,
        )

    @staticmethod
    def _payment(raw: dict) -> EBayPaymentPolicy:
        return EBayPaymentPolicy(policy_id=raw["paymentPolicyId"], name=raw["name"],
                                 marketplace_id=raw.get("marketplaceId", ""))

    @staticmethod
    def _location(raw: dict) -> EBayInventoryLocation:
        return EBayInventoryLocation(
            merchant_location_key=raw["merchantLocationKey"],
            name=raw.get("name") or raw["merchantLocationKey"],
            location_types=raw.get("locationTypes") or [], status=raw.get("merchantLocationStatus", "UNKNOWN"),
        )


EBayPolicyClient = EBaySellerPolicyDiscovery
