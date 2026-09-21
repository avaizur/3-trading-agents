from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.schemas import (
    AgentEvaluationRecord,
    AgentRole,
    CandidateStatus,
    DraftReviewStatus,
    EBayListingDraft,
    ProductCandidate,
    ProductLane,
    ReturnPostagePayer,
    ReturnRoute,
    SupplierBackedProduct,
    SupplierPolicyRules,
    SupplierProfitStatus,
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


def test_candidate_round_trip_and_status_update():
    store = build_store()

    candidate = ProductCandidate(
        candidate_id="CAND-TEST-1",
        sku="PET-TEST",
        title="Test Product",
        supplier_id="Go Dropship",
        supplier_cost=10.0,
        target_price=20.0,
    )

    saved = store.save_candidate(candidate)

    assert saved.created_at is not None
    assert saved.updated_at is not None

    loaded = store.get_candidate("CAND-TEST-1")

    assert loaded is not None
    assert loaded.candidate_id == "CAND-TEST-1"
    assert loaded.status == CandidateStatus.NEW

    updated = store.update_candidate_status(
        "CAND-TEST-1",
        CandidateStatus.VERIFIED,
        notes="Supplier verified",
    )

    assert updated.status == CandidateStatus.VERIFIED
    assert updated.notes == "Supplier verified"


def test_list_candidates_filters_status():
    store = build_store()

    first = ProductCandidate(
        candidate_id="CAND-1",
        sku="SKU-1",
        title="One",
        supplier_id="Supplier",
        supplier_cost=10.0,
        target_price=20.0,
    )

    second = ProductCandidate(
        candidate_id="CAND-2",
        sku="SKU-2",
        title="Two",
        supplier_id="Supplier",
        supplier_cost=10.0,
        target_price=20.0,
        status=CandidateStatus.REJECTED,
    )

    store.save_candidate(first)
    store.save_candidate(second)

    rejected = store.list_candidates(
        status=CandidateStatus.REJECTED
    )

    assert len(rejected) == 1
    assert rejected[0].candidate_id == "CAND-2"


def test_draft_round_trip_and_approval():
    store = build_store()

    draft = EBayListingDraft(
        draft_id="DRAFT-EBAY-PET-TEST",
        candidate_id="CAND-TEST-1",
        title="Test Product",
        sku="PET-TEST",
        price=20.0,
        quantity=1,
        description="Test description",
        supplier_reference="Go Dropship",
        expected_profit=5.0,
        expected_margin=0.25,
    )

    saved = store.save_draft(draft)

    assert saved.created_at is not None
    assert saved.status == DraftReviewStatus.DRAFT_CREATED

    loaded = store.get_draft("DRAFT-EBAY-PET-TEST")

    assert loaded is not None
    assert loaded.sku == "PET-TEST"

    approved = store.update_draft_status(
        "DRAFT-EBAY-PET-TEST",
        DraftReviewStatus.APPROVED_TO_PUBLISH,
        reviewed_by="human-reviewer",
    )

    assert approved.status == DraftReviewStatus.APPROVED_TO_PUBLISH
    assert approved.reviewed_by == "human-reviewer"
    assert approved.reviewed_at is not None


def test_get_draft_by_candidate_id():
    store = build_store()

    draft = EBayListingDraft(
        candidate_id="CAND-XYZ",
        title="Test Product",
        sku="SKU-XYZ",
        price=25.0,
        description="Description",
        supplier_reference="Supplier",
        expected_profit=6.0,
        expected_margin=0.24,
    )

    saved = store.save_draft(draft)

    loaded = store.get_draft_by_candidate_id("CAND-XYZ")

    assert loaded is not None
    assert loaded.draft_id == saved.draft_id


def test_agent_evaluation_round_trip():
    store = build_store()

    evaluation = AgentEvaluationRecord(
        pipeline_run_id="RUN-123",
        supplier_sku="PET-TEST",
        supplier_name="Go Dropship",
        agent_role=AgentRole.SCOUT,
        recommendation="PROCEED",
        score=80.0,
        confidence=0.9,
        evidence_snapshot={"market": "healthy"},
        evaluation_details={"reason": "good demand"},
    )

    saved = store.save_agent_evaluation(evaluation)

    assert saved.created_at is not None

    loaded = store.list_agent_evaluations(
        pipeline_run_id="RUN-123"
    )

    assert len(loaded) == 1
    assert loaded[0].agent_role == AgentRole.SCOUT
    assert loaded[0].recommendation == "PROCEED"
    assert loaded[0].evidence_snapshot == {"market": "healthy"}
