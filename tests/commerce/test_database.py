import sqlite3
from src.commerce.database import CommerceDatabase, init_commerce_database
from src.commerce.schemas import (
    CandidateStatus,
    Platform,
    ProductCandidate,
    SupplierCheckRecord,
    SupplierType,
)


def test_database_initialises(tmp_path):
    db_path = tmp_path / "test_commerce.db"
    init_commerce_database(str(db_path))

    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert "product_candidates" in tables
    assert "supplier_checks" in tables
    assert "manual_supplier_matches" in tables


def test_save_and_get_candidate(tmp_path):
    db_path = tmp_path / "test_candidates.db"
    db = CommerceDatabase(str(db_path))

    candidate = ProductCandidate(
        candidate_id="CAND-001",
        sku="SKU-TUMBLER-20",
        title="20oz Stainless Tumbler",
        supplier_id="WHOLESALE-SUP-1",
        target_platform=Platform.EBAY,
        supplier_cost=10.0,
        target_price=24.99,
        shipping_cost=3.50,
        estimated_fee=3.61,
        estimated_profit=7.88,
        estimated_margin_pct=0.315,
        status=CandidateStatus.NEW,
        notes="Promising scout opportunity",
    )

    saved = db.save_candidate(candidate)
    assert saved.candidate_id == "CAND-001"
    assert saved.status == CandidateStatus.NEW

    loaded = db.get_candidate("CAND-001")
    assert loaded is not None
    assert loaded.candidate_id == "CAND-001"
    assert loaded.sku == "SKU-TUMBLER-20"
    assert loaded.title == "20oz Stainless Tumbler"
    assert loaded.target_platform == Platform.EBAY
    assert loaded.supplier_cost == 10.0
    assert loaded.target_price == 24.99
    assert loaded.shipping_cost == 3.50
    assert loaded.estimated_profit == 7.88
    assert loaded.status == CandidateStatus.NEW
    assert loaded.notes == "Promising scout opportunity"
    assert loaded.created_at is not None
    assert loaded.updated_at is not None


def test_save_candidate_upsert(tmp_path):
    db = CommerceDatabase(str(tmp_path / "upsert.db"))

    candidate = ProductCandidate(
        candidate_id="CAND-UPSERT",
        sku="SKU-UP-1",
        title="Original Title",
        supplier_id="SUP-1",
        supplier_cost=15.0,
        target_price=30.0,
        status=CandidateStatus.NEW,
    )
    db.save_candidate(candidate)

    # Update fields and save again
    candidate.title = "Updated Title"
    candidate.target_price = 35.0
    db.save_candidate(candidate)

    loaded = db.get_candidate("CAND-UPSERT")
    assert loaded is not None
    assert loaded.title == "Updated Title"
    assert loaded.target_price == 35.0


def test_list_candidates_and_filter_by_status(tmp_path):
    db = CommerceDatabase(str(tmp_path / "filter.db"))

    for i in range(5):
        status = CandidateStatus.NEW if i < 3 else CandidateStatus.VERIFIED
        db.save_candidate(
            ProductCandidate(
                candidate_id=f"CAND-TEST-{i}",
                sku=f"SKU-{i}",
                title=f"Product {i}",
                supplier_id="SUP-1",
                supplier_cost=10.0 + i,
                target_price=20.0 + i,
                status=status,
            )
        )

    all_candidates = db.list_candidates()
    assert len(all_candidates) == 5

    new_candidates = db.list_candidates(status=CandidateStatus.NEW)
    assert len(new_candidates) == 3

    verified_candidates = db.list_candidates(status=CandidateStatus.VERIFIED)
    assert len(verified_candidates) == 2

    # Pagination test
    paginated = db.list_candidates(limit=2, offset=0)
    assert len(paginated) == 2
    assert paginated[0].candidate_id == "CAND-TEST-0"


def test_update_candidate_status(tmp_path):
    db = CommerceDatabase(str(tmp_path / "status.db"))

    db.save_candidate(
        ProductCandidate(
            candidate_id="CAND-STAT-1",
            sku="SKU-STAT",
            title="Status Test Product",
            supplier_id="SUP-1",
            supplier_cost=12.0,
            target_price=25.0,
            status=CandidateStatus.NEW,
        )
    )

    updated = db.update_candidate_status(
        candidate_id="CAND-STAT-1",
        new_status=CandidateStatus.REJECTED,
        rejection_reason="Insufficient margin buffer",
        notes="Rejected in preliminary screening",
    )

    assert updated.status == CandidateStatus.REJECTED
    assert updated.rejection_reason == "Insufficient margin buffer"
    assert updated.notes == "Rejected in preliminary screening"

    loaded = db.get_candidate("CAND-STAT-1")
    assert loaded.status == CandidateStatus.REJECTED
    assert loaded.rejection_reason == "Insufficient margin buffer"


def test_record_and_get_supplier_checks(tmp_path):
    db = CommerceDatabase(str(tmp_path / "checks.db"))

    # Save candidate first to satisfy relational integrity
    db.save_candidate(
        ProductCandidate(
            candidate_id="CAND-001",
            sku="SKU-W-1",
            title="Wholesale Stainless Tumbler",
            supplier_id="WHOLESALE-01",
            supplier_cost=10.0,
            target_price=20.0,
        )
    )

    check = SupplierCheckRecord(
        candidate_id="CAND-001",
        supplier_id="WHOLESALE-01",
        sku="SKU-W-1",
        supplier_type=SupplierType.WHOLESALE,
        is_valid=True,
        retail_dropshipping_blocked=False,
        reason="Passed all supplier checks",
        passed_checks=["supplier_type_non_retail", "reselling_authorized"],
        warnings=[],
    )

    saved_check = db.record_supplier_check(check)
    assert saved_check.id is not None
    assert saved_check.is_valid is True
    assert saved_check.checked_at is not None

    checks = db.get_supplier_checks(candidate_id="CAND-001")
    assert len(checks) == 1
    assert checks[0].supplier_id == "WHOLESALE-01"
    assert checks[0].is_valid is True
    assert checks[0].retail_dropshipping_blocked is False
    assert "supplier_type_non_retail" in checks[0].passed_checks

    latest = db.get_latest_supplier_check("CAND-001")
    assert latest is not None
    assert latest.sku == "SKU-W-1"

    # Also test standalone check without candidate (candidate_id=None)
    standalone_check = SupplierCheckRecord(
        candidate_id=None,
        supplier_id="DISTRIBUTOR-99",
        sku="SKU-DIST-99",
        supplier_type=SupplierType.DISTRIBUTOR,
        is_valid=True,
        reason="General supplier verification",
        passed_checks=["supplier_type_non_retail"],
    )
    saved_standalone = db.record_supplier_check(standalone_check)
    assert saved_standalone.id is not None
    dist_checks = db.get_supplier_checks(supplier_id="DISTRIBUTOR-99")
    assert len(dist_checks) == 1
    assert dist_checks[0].candidate_id is None


def test_in_memory_database():
    db = CommerceDatabase(":memory:")

    db.save_candidate(
        ProductCandidate(
            candidate_id="CAND-MEM",
            sku="SKU-MEM",
            title="In Memory Product",
            supplier_id="SUP-MEM",
            supplier_cost=5.0,
            target_price=15.0,
        )
    )

    found = db.get_candidate("CAND-MEM")
    assert found is not None
    assert found.title == "In Memory Product"
    db.close()
