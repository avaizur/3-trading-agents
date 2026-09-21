from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.schemas import (
    ProductLane,
    ReturnPostagePayer,
    ReturnRoute,
    SupplierBackedProduct,
    SupplierPolicyRules,
)


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[(Item["PK"], Item["SK"])] = Item
        return {}

    def get_item(self, Key):
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": item} if item else {}

    def scan(self, **kwargs):
        entity_type = kwargs["ExpressionAttributeValues"][":entity_type"]
        return {
            "Items": [
                item
                for item in self.items.values()
                if item.get("entity_type") == entity_type
            ]
        }


class FakeDynamoResource:
    def __init__(self):
        self.table = FakeTable()

    def Table(self, table_name):
        return self.table


def build_store():
    resource = FakeDynamoResource()
    return DynamoCommerceStore(
        table_name="test-commerce",
        dynamodb_resource=resource,
    )


def test_supplier_backed_product_round_trip():
    store = build_store()

    product = SupplierBackedProduct(
        supplier_name="Go Dropship",
        supplier_sku="PET-TEST",
        product_name="Test Product",
        supplier_cost=10.0,
        lane=ProductLane.EVERGREEN,
    )

    store.save_supplier_backed_product(product)

    loaded = store.get_supplier_backed_product(
        "Go Dropship",
        "PET-TEST",
    )

    assert loaded == product


def test_list_supplier_backed_products():
    store = build_store()

    first = SupplierBackedProduct(
        supplier_name="Go Dropship",
        supplier_sku="PET-1",
        product_name="Product One",
        supplier_cost=10.0,
        lane=ProductLane.EVERGREEN,
    )

    second = SupplierBackedProduct(
        supplier_name="Maibo",
        supplier_sku="KVM-1",
        product_name="KVM Switch",
        supplier_cost=40.0,
        lane=ProductLane.EVERGREEN,
    )

    store.save_supplier_backed_product(first)
    store.save_supplier_backed_product(second)

    loaded = store.list_supplier_backed_products()

    assert len(loaded) == 2
    assert first in loaded
    assert second in loaded


def test_supplier_policy_round_trip():
    store = build_store()

    rules = SupplierPolicyRules(
        supplier_id="Go Dropship",
        dispatch_time_days=2,
        shipping_services=["Tracked"],
        remote_surcharge=0.0,
        blind_ship=True,
        return_route=ReturnRoute.SUPPLIER,
        rma_required=True,
        return_postage=ReturnPostagePayer.BUYER,
        supplier_fault_resolution="Refund or replacement after evidence",
    )

    store.save_supplier_policy_rules(rules)

    loaded = store.get_supplier_policy_rules("Go Dropship")

    assert loaded == rules
