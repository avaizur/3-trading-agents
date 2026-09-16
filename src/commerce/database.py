import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Generator, Optional, Union

from src.commerce.schemas import (
    CandidateStatus,
    DraftReviewStatus,
    EBayListingDraft,
    Platform,
    ProductCandidate,
    SupplierBackedProduct,
    SupplierMarketValidationResult,
    SupplierCheckRecord,
    SupplierPolicyRules,
    EBayPolicySnapshot,
    EBayFulfillmentPolicy,
    EBayReturnPolicy,
    EBayPaymentPolicy,
    EBayInventoryLocation,
    SupplierType,
    AgentEvaluationRecord,
    HumanDecisionRecord,
    RealizedOutcomeRecord,
    AgentRole,
    HumanDecisionType,
)

COMMERCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS product_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT UNIQUE NOT NULL,
    sku TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    supplier_id TEXT NOT NULL,
    target_platform TEXT NOT NULL DEFAULT 'EBAY',
    supplier_cost REAL NOT NULL,
    target_price REAL NOT NULL,
    shipping_cost REAL NOT NULL DEFAULT 0.0,
    estimated_fee REAL NOT NULL DEFAULT 0.0,
    estimated_profit REAL,
    estimated_margin_pct REAL,
    supplier_profit_status TEXT NOT NULL DEFAULT 'NEEDS_SUPPLIER_DATA',
    status TEXT NOT NULL DEFAULT 'NEW',
    rejection_reason TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidates_status ON product_candidates(status);
CREATE INDEX IF NOT EXISTS idx_candidates_sku ON product_candidates(sku);

CREATE TABLE IF NOT EXISTS supplier_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT,
    supplier_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    supplier_type TEXT NOT NULL,
    is_valid INTEGER NOT NULL,
    retail_dropshipping_blocked INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    passed_checks TEXT NOT NULL,
    warnings TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    FOREIGN KEY(candidate_id) REFERENCES product_candidates(candidate_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_checks_candidate_id ON supplier_checks(candidate_id);
CREATE INDEX IF NOT EXISTS idx_checks_supplier_id ON supplier_checks(supplier_id);

CREATE TABLE IF NOT EXISTS manual_supplier_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ebay_item_id TEXT NOT NULL,
    supplier_name TEXT,
    sku TEXT,
    cost REAL,
    shipping REAL,
    stock INTEGER,
    direct_ship INTEGER,
    verification_status TEXT NOT NULL,
    supplier_status TEXT NOT NULL,
    expected_profit REAL,
    expected_margin REAL,
    final_outcome TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_manual_matches_item_id
ON manual_supplier_matches(ebay_item_id);

CREATE TABLE IF NOT EXISTS supplier_backed_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT NOT NULL,
    supplier_sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    supplier_cost REAL NOT NULL CHECK (supplier_cost > 0),
    lane TEXT NOT NULL CHECK (lane IN ('EVERGREEN', 'SEASONAL')),
    market_price REAL,
    platform_fees REAL,
    return_allowance REAL,
    market_price_validated INTEGER NOT NULL DEFAULT 0,
    platform_fees_validated INTEGER NOT NULL DEFAULT 0,
    return_allowance_validated INTEGER NOT NULL DEFAULT 0,
    expected_profit REAL,
    expected_margin REAL,
    market_validation_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (market_validation_status IN ('PENDING', 'PASS', 'REJECT')),
    validation_reason TEXT,
    profitable INTEGER NOT NULL DEFAULT 0,
    auto_approved INTEGER NOT NULL DEFAULT 0 CHECK (auto_approved = 0),
    published INTEGER NOT NULL DEFAULT 0 CHECK (published = 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(supplier_name, supplier_sku),
    CHECK (
        profitable = 0 OR (
            market_price_validated = 1 AND
            platform_fees_validated = 1 AND
            return_allowance_validated = 1
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_supplier_backed_lane
ON supplier_backed_products(lane);

CREATE TABLE IF NOT EXISTS supplier_market_validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT NOT NULL,
    supplier_sku TEXT NOT NULL,
    marketplace_sale_price REAL NOT NULL CHECK (marketplace_sale_price > 0),
    platform_fee_estimate REAL NOT NULL CHECK (platform_fee_estimate >= 0),
    return_allowance REAL NOT NULL CHECK (return_allowance >= 0),
    expected_profit REAL NOT NULL,
    expected_margin REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PASS', 'REJECT')),
    reason TEXT NOT NULL,
    validated_at TEXT NOT NULL,
    FOREIGN KEY(supplier_name, supplier_sku)
        REFERENCES supplier_backed_products(supplier_name, supplier_sku)
);

CREATE INDEX IF NOT EXISTS idx_supplier_market_validations_product
ON supplier_market_validations(supplier_name, supplier_sku);

CREATE TABLE IF NOT EXISTS ebay_listing_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id TEXT UNIQUE NOT NULL,
    candidate_id TEXT,
    title TEXT NOT NULL,
    sku TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    category_placeholder TEXT NOT NULL,
    shipping TEXT NOT NULL,
    shipping_placeholder TEXT NOT NULL,
    supplier_reference TEXT NOT NULL,
    expected_profit REAL NOT NULL,
    expected_margin REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT_CREATED',
    human_approval_required INTEGER NOT NULL DEFAULT 1,
    reviewed_by TEXT,
    reviewed_at TEXT,
    rejection_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(candidate_id) REFERENCES product_candidates(candidate_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_drafts_candidate_id ON ebay_listing_drafts(candidate_id);
CREATE INDEX IF NOT EXISTS idx_drafts_sku ON ebay_listing_drafts(sku);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON ebay_listing_drafts(status);

CREATE TABLE IF NOT EXISTS supplier_policy_rules (
    supplier_id TEXT PRIMARY KEY,
    dispatch_time_days INTEGER NOT NULL,
    shipping_services TEXT NOT NULL,
    remote_surcharge REAL NOT NULL,
    blind_ship INTEGER NOT NULL,
    return_route TEXT NOT NULL,
    rma_required INTEGER NOT NULL,
    return_postage TEXT NOT NULL,
    supplier_fault_resolution TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ebay_policy_snapshots (
    policy_type TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    name TEXT NOT NULL,
    marketplace_id TEXT NOT NULL,
    settings TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    PRIMARY KEY (policy_type, policy_id)
);

CREATE TABLE IF NOT EXISTS agent_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_run_id TEXT NOT NULL,
    supplier_sku TEXT NOT NULL,
    supplier_name TEXT NOT NULL,
    agent_role TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    score REAL,
    confidence REAL,
    evidence_snapshot TEXT NOT NULL DEFAULT '{}',
    evaluation_details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_evals_sku ON agent_evaluations(supplier_sku);
CREATE INDEX IF NOT EXISTS idx_agent_evals_run ON agent_evaluations(pipeline_run_id);

CREATE TABLE IF NOT EXISTS human_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    supplier_sku TEXT NOT NULL,
    pipeline_run_id TEXT,
    decision TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    reason_category TEXT NOT NULL,
    notes TEXT,
    price_adjustment REAL,
    decided_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_human_decisions_sku ON human_decisions(supplier_sku);
CREATE INDEX IF NOT EXISTS idx_human_decisions_cand ON human_decisions(candidate_id);

CREATE TABLE IF NOT EXISTS commerce_realized_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_sku TEXT NOT NULL,
    supplier_name TEXT NOT NULL,
    listing_id TEXT,
    listed_at TEXT,
    first_sale_at TEXT,
    days_to_first_sale INTEGER,
    units_sold INTEGER NOT NULL DEFAULT 0,
    actual_sale_price REAL,
    actual_supplier_cost REAL,
    actual_platform_fees REAL,
    realized_net_profit REAL,
    realized_margin_pct REAL,
    return_count INTEGER NOT NULL DEFAULT 0,
    return_reasons TEXT NOT NULL DEFAULT '[]',
    supplier_fulfillment_issue TEXT,
    seasonal_window_missed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(supplier_name, supplier_sku)
);

CREATE INDEX IF NOT EXISTS idx_outcomes_sku ON commerce_realized_outcomes(supplier_sku);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommerceDatabase:
    """SQLite database manager for commerce product candidates and supplier checks."""

    def __init__(
        self,
        db_path: str = "data/commerce.db",
        shared_conn: Optional[sqlite3.Connection] = None,
    ):
        self.db_path = db_path
        self._shared_conn = shared_conn
        if self.db_path == ":memory:" and self._shared_conn is None:
            self._shared_conn = sqlite3.connect(":memory:")
            self._shared_conn.row_factory = sqlite3.Row
            self._shared_conn.execute("PRAGMA foreign_keys = ON;")
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        if self._shared_conn is not None:
            with self._shared_conn:
                yield self._shared_conn
        else:
            db_file = Path(self.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

    def init_db(self) -> None:
        with self.get_connection() as conn:
            conn.executescript(COMMERCE_SCHEMA)
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(product_candidates)")
            }
            if "supplier_profit_status" not in columns:
                conn.execute(
                    "ALTER TABLE product_candidates ADD COLUMN supplier_profit_status "
                    "TEXT NOT NULL DEFAULT 'NEEDS_SUPPLIER_DATA'"
                )
            if "category" not in columns:
                conn.execute("ALTER TABLE product_candidates ADD COLUMN category TEXT")
            staged_columns = {
                row[1] for row in conn.execute(
                    "PRAGMA table_info(supplier_backed_products)"
                )
            }
            staged_additions = {
                "expected_profit": "REAL",
                "expected_margin": "REAL",
                "market_validation_status": "TEXT NOT NULL DEFAULT 'PENDING'",
                "validation_reason": "TEXT",
            }
            for name, definition in staged_additions.items():
                if name not in staged_columns:
                    conn.execute(
                        f"ALTER TABLE supplier_backed_products ADD COLUMN {name} {definition}"
                    )

            supplier_policy_columns = {
                row[1] for row in conn.execute(
                    "PRAGMA table_info(supplier_policy_rules)"
                )
            }
            if "supplier_fault_resolution" not in supplier_policy_columns:
                conn.execute(
                    "ALTER TABLE supplier_policy_rules "
                    "ADD COLUMN supplier_fault_resolution TEXT"
                )

    def close(self) -> None:
        if self._shared_conn is not None:
            self._shared_conn.close()
            self._shared_conn = None

    def save_supplier_policy_rules(self, rules: SupplierPolicyRules) -> SupplierPolicyRules:
        """Upsert supplier constraints; no marketplace operation is performed."""
        now = _now_iso()
        with self.get_connection() as conn:
            conn.execute(
                """INSERT INTO supplier_policy_rules (
                    supplier_id, dispatch_time_days, shipping_services, remote_surcharge,
                    blind_ship, return_route, rma_required, return_postage,
                    supplier_fault_resolution, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(supplier_id) DO UPDATE SET
                    dispatch_time_days=excluded.dispatch_time_days,
                    shipping_services=excluded.shipping_services,
                    remote_surcharge=excluded.remote_surcharge,
                    blind_ship=excluded.blind_ship,
                    return_route=excluded.return_route,
                    rma_required=excluded.rma_required,
                    return_postage=excluded.return_postage,
                    supplier_fault_resolution=excluded.supplier_fault_resolution,
                    updated_at=excluded.updated_at""",
                (
                    rules.supplier_id,
                    rules.dispatch_time_days,
                    json.dumps(rules.shipping_services),
                    rules.remote_surcharge,
                    int(rules.blind_ship),
                    rules.return_route.value,
                    int(rules.rma_required),
                    rules.return_postage.value,
                    rules.supplier_fault_resolution,
                    now,
                ),
            )
        loaded = self.get_supplier_policy_rules(rules.supplier_id)
        assert loaded is not None
        return loaded

    def get_supplier_policy_rules(self, supplier_id: str) -> Optional[SupplierPolicyRules]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM supplier_policy_rules WHERE supplier_id = ?",
                               (supplier_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["shipping_services"] = json.loads(data["shipping_services"])
        data["blind_ship"] = bool(data["blind_ship"])
        data["rma_required"] = bool(data["rma_required"])
        return SupplierPolicyRules(**data)

    # Short aliases retained for callers that treat these as supplier rules.
    save_supplier_rules = save_supplier_policy_rules
    get_supplier_rules = get_supplier_policy_rules

    def save_ebay_policy_snapshot(self, snapshot: EBayPolicySnapshot) -> None:
        """Persist only normalized matching fields, replacing the prior cache."""
        now = _now_iso()
        groups = (
            ("fulfillment", snapshot.fulfillment_policies),
            ("return", snapshot.return_policies),
            ("payment", snapshot.payment_policies),
            ("location", snapshot.inventory_locations),
        )
        with self.get_connection() as conn:
            conn.execute("DELETE FROM ebay_policy_snapshots WHERE marketplace_id = ?",
                         (snapshot.marketplace_id,))
            for kind, records in groups:
                for record in records:
                    data = record.model_dump(mode="json")
                    policy_id = data.pop("policy_id", None)
                    if policy_id is None:
                        policy_id = data.pop("merchant_location_key")
                    name = data.pop("name")
                    marketplace = data.pop("marketplace_id", snapshot.marketplace_id)
                    conn.execute(
                        "INSERT OR REPLACE INTO ebay_policy_snapshots "
                        "(policy_type, policy_id, name, marketplace_id, settings, discovered_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (kind, policy_id, name, marketplace, json.dumps(data), now),
                    )

    def get_ebay_policy_snapshot(self, marketplace_id: str) -> EBayPolicySnapshot:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ebay_policy_snapshots WHERE marketplace_id = ? ORDER BY policy_type, policy_id",
                (marketplace_id,),
            ).fetchall()
        groups = {"fulfillment": [], "return": [], "payment": [], "location": []}
        models = {"fulfillment": EBayFulfillmentPolicy, "return": EBayReturnPolicy,
                  "payment": EBayPaymentPolicy, "location": EBayInventoryLocation}
        for row in rows:
            data = json.loads(row["settings"])
            id_name = "merchant_location_key" if row["policy_type"] == "location" else "policy_id"
            data.update({id_name: row["policy_id"], "name": row["name"]})
            if row["policy_type"] != "location":
                data["marketplace_id"] = row["marketplace_id"]
            groups[row["policy_type"]].append(models[row["policy_type"]](**data))
        return EBayPolicySnapshot(
            marketplace_id=marketplace_id, fulfillment_policies=groups["fulfillment"],
            return_policies=groups["return"], payment_policies=groups["payment"],
            inventory_locations=groups["location"],
        )

    def save_candidate(self, candidate: ProductCandidate) -> ProductCandidate:
        now = _now_iso()
        created_at = (
            candidate.created_at.isoformat()
            if candidate.created_at
            else now
        )
        updated_at = (
            candidate.updated_at.isoformat()
            if candidate.updated_at
            else now
        )

        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO product_candidates (
                    candidate_id, sku, title, category, supplier_id, target_platform,
                    supplier_cost, target_price, shipping_cost, estimated_fee,
                    estimated_profit, estimated_margin_pct, supplier_profit_status,
                    status, rejection_reason, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    sku=excluded.sku,
                    title=excluded.title,
                    category=excluded.category,
                    supplier_id=excluded.supplier_id,
                    target_platform=excluded.target_platform,
                    supplier_cost=excluded.supplier_cost,
                    target_price=excluded.target_price,
                    shipping_cost=excluded.shipping_cost,
                    estimated_fee=excluded.estimated_fee,
                    estimated_profit=excluded.estimated_profit,
                    estimated_margin_pct=excluded.estimated_margin_pct,
                    supplier_profit_status=excluded.supplier_profit_status,
                    status=excluded.status,
                    rejection_reason=excluded.rejection_reason,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at;
                """,
                (
                    candidate.candidate_id,
                    candidate.sku,
                    candidate.title,
                    candidate.category,
                    candidate.supplier_id,
                    candidate.target_platform.value,
                    candidate.supplier_cost,
                    candidate.target_price,
                    candidate.shipping_cost,
                    candidate.estimated_fee,
                    candidate.estimated_profit,
                    candidate.estimated_margin_pct,
                    candidate.supplier_profit_status.value,
                    candidate.status.value,
                    candidate.rejection_reason,
                    candidate.notes,
                    created_at,
                    updated_at,
                ),
            )
            saved_id = cursor.lastrowid

        loaded = self.get_candidate(candidate.candidate_id)
        if loaded is not None:
            return loaded
        if candidate.id is None and saved_id:
            candidate.id = saved_id
        return candidate

    def get_candidate(self, candidate_id: str) -> Optional[ProductCandidate]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM product_candidates WHERE candidate_id = ?",
                (candidate_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            return ProductCandidate(**data)

    def list_candidates(
        self,
        status: Optional[Union[CandidateStatus, str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProductCandidate]:
        status_val = status.value if isinstance(status, CandidateStatus) else status
        query = "SELECT * FROM product_candidates"
        params: list = []
        if status_val is not None:
            query += " WHERE status = ?"
            params.append(status_val)
        query += " ORDER BY id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self.get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [ProductCandidate(**dict(r)) for r in rows]

    def get_candidates_by_sku(self, sku: str) -> list[ProductCandidate]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM product_candidates WHERE sku = ? ORDER BY id ASC",
                (sku,),
            ).fetchall()
            return [ProductCandidate(**dict(row)) for row in rows]

    def update_candidate_status(
        self,
        candidate_id: str,
        new_status: Union[CandidateStatus, str],
        rejection_reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ProductCandidate:
        status_val = (
            new_status.value
            if isinstance(new_status, CandidateStatus)
            else str(new_status)
        )
        now = _now_iso()

        with self.get_connection() as conn:
            # Check candidate existence
            existing = conn.execute(
                "SELECT * FROM product_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if not existing:
                raise KeyError(f"Candidate '{candidate_id}' not found.")

            conn.execute(
                """
                UPDATE product_candidates
                SET status = ?,
                    rejection_reason = COALESCE(?, rejection_reason),
                    notes = COALESCE(?, notes),
                    updated_at = ?
                WHERE candidate_id = ?
                """,
                (status_val, rejection_reason, notes, now, candidate_id),
            )

        updated = self.get_candidate(candidate_id)
        if not updated:
            raise KeyError(f"Candidate '{candidate_id}' not found after update.")
        return updated

    def record_supplier_check(
        self,
        check: SupplierCheckRecord,
    ) -> SupplierCheckRecord:
        now = _now_iso()
        checked_at = (
            check.checked_at.isoformat()
            if check.checked_at
            else now
        )
        passed_checks_json = json.dumps(check.passed_checks)
        warnings_json = json.dumps(check.warnings)

        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO supplier_checks (
                    candidate_id, supplier_id, sku, supplier_type,
                    is_valid, retail_dropshipping_blocked, reason,
                    passed_checks, warnings, checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    check.candidate_id,
                    check.supplier_id,
                    check.sku,
                    check.supplier_type.value,
                    1 if check.is_valid else 0,
                    1 if check.retail_dropshipping_blocked else 0,
                    check.reason,
                    passed_checks_json,
                    warnings_json,
                    checked_at,
                ),
            )
            saved_id = cursor.lastrowid

        check_copy = check.model_copy()
        check_copy.id = saved_id
        if check_copy.checked_at is None:
            check_copy.checked_at = datetime.fromisoformat(checked_at)
        return check_copy

    def get_supplier_checks(
        self,
        candidate_id: Optional[str] = None,
        supplier_id: Optional[str] = None,
    ) -> list[SupplierCheckRecord]:
        conditions = []
        params = []
        if candidate_id is not None:
            conditions.append("candidate_id = ?")
            params.append(candidate_id)
        if supplier_id is not None:
            conditions.append("supplier_id = ?")
            params.append(supplier_id)

        query = "SELECT * FROM supplier_checks"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id ASC"

        with self.get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if isinstance(data.get("passed_checks"), str):
                    data["passed_checks"] = json.loads(data["passed_checks"])
                if isinstance(data.get("warnings"), str):
                    data["warnings"] = json.loads(data["warnings"])
                data["is_valid"] = bool(data["is_valid"])
                data["retail_dropshipping_blocked"] = bool(
                    data["retail_dropshipping_blocked"]
                )
                results.append(SupplierCheckRecord(**data))
            return results

    def get_latest_supplier_check(
        self,
        candidate_id: str,
    ) -> Optional[SupplierCheckRecord]:
        checks = self.get_supplier_checks(candidate_id=candidate_id)
        return checks[-1] if checks else None

    def record_manual_supplier_match(self, values: dict) -> int:
        """Persist one manual verification outcome, including rejected attempts."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO manual_supplier_matches (
                    ebay_item_id, supplier_name, sku, cost, shipping, stock,
                    direct_ship, verification_status, supplier_status,
                    expected_profit, expected_margin, final_outcome, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["ebay_item_id"], values.get("supplier_name"),
                    values.get("sku"), values.get("cost"), values.get("shipping"),
                    values.get("stock"),
                    None if values.get("direct_ship") is None
                    else int(values["direct_ship"]),
                    values["verification_status"], values["supplier_status"],
                    values.get("expected_profit"), values.get("expected_margin"),
                    values["final_outcome"], _now_iso(),
                ),
            )
            return cursor.lastrowid

    def import_supplier_backed_products(
        self, products: list[SupplierBackedProduct]
    ) -> list[SupplierBackedProduct]:
        """Atomically upsert locked supplier facts without changing review state."""
        if not products:
            raise ValueError("Supplier product batch is empty.")
        keys = [(p.supplier_name, p.supplier_sku) for p in products]
        if len(keys) != len(set(keys)):
            raise ValueError("Supplier product batch contains duplicate SKUs.")
        now = _now_iso()
        with self.get_connection() as conn:
            for product in products:
                conn.execute(
                    """
                    INSERT INTO supplier_backed_products (
                        supplier_name, supplier_sku, product_name, supplier_cost,
                        lane, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(supplier_name, supplier_sku) DO UPDATE SET
                        product_name=excluded.product_name,
                        supplier_cost=excluded.supplier_cost,
                        lane=excluded.lane,
                        updated_at=excluded.updated_at
                    """,
                    (
                        product.supplier_name, product.supplier_sku,
                        product.product_name, product.supplier_cost,
                        product.lane.value, now, now,
                    ),
                )
        return [
            self.get_supplier_backed_product(name, sku)
            for name, sku in keys
        ]

    def get_supplier_backed_product(
        self, supplier_name: str, supplier_sku: str
    ) -> Optional[SupplierBackedProduct]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM supplier_backed_products "
                "WHERE supplier_name = ? AND supplier_sku = ?",
                (supplier_name, supplier_sku),
            ).fetchone()
            return self._supplier_backed_from_row(row) if row else None

    def list_supplier_backed_products(self) -> list[SupplierBackedProduct]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM supplier_backed_products ORDER BY id ASC"
            ).fetchall()
            return [self._supplier_backed_from_row(row) for row in rows]

    def save_supplier_market_validations(
        self, results: list[SupplierMarketValidationResult]
    ) -> list[SupplierMarketValidationResult]:
        """Atomically persist an audit record and current result for a batch."""
        if not results:
            raise ValueError("Market validation batch is empty.")
        keys = [(r.supplier_name, r.supplier_sku) for r in results]
        if len(keys) != len(set(keys)):
            raise ValueError("Market validation batch contains duplicate products.")
        now = _now_iso()
        saved: list[SupplierMarketValidationResult] = []
        with self.get_connection() as conn:
            for result in results:
                existing = conn.execute(
                    "SELECT 1 FROM supplier_backed_products "
                    "WHERE supplier_name = ? AND supplier_sku = ?",
                    (result.supplier_name, result.supplier_sku),
                ).fetchone()
                if not existing:
                    raise KeyError(
                        f"Staged product '{result.supplier_name}/{result.supplier_sku}' not found."
                    )
                cursor = conn.execute(
                    """
                    INSERT INTO supplier_market_validations (
                        supplier_name, supplier_sku, marketplace_sale_price,
                        platform_fee_estimate, return_allowance, expected_profit,
                        expected_margin, status, reason, validated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.supplier_name, result.supplier_sku,
                        result.marketplace_sale_price, result.platform_fee_estimate,
                        result.return_allowance, result.expected_profit,
                        result.expected_margin, result.status.value, result.reason, now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE supplier_backed_products SET
                        market_price = ?, platform_fees = ?, return_allowance = ?,
                        market_price_validated = 1, platform_fees_validated = 1,
                        return_allowance_validated = 1, expected_profit = ?,
                        expected_margin = ?, market_validation_status = ?,
                        validation_reason = ?, profitable = ?, updated_at = ?
                    WHERE supplier_name = ? AND supplier_sku = ?
                    """,
                    (
                        result.marketplace_sale_price, result.platform_fee_estimate,
                        result.return_allowance, result.expected_profit,
                        result.expected_margin, result.status.value, result.reason,
                        int(result.status.value == "PASS"), now,
                        result.supplier_name, result.supplier_sku,
                    ),
                )
                saved.append(result.model_copy(update={
                    "id": cursor.lastrowid,
                    "validated_at": datetime.fromisoformat(now),
                }))
        return saved

    def get_supplier_market_validations(
        self, supplier_name: str, supplier_sku: str
    ) -> list[SupplierMarketValidationResult]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM supplier_market_validations "
                "WHERE supplier_name = ? AND supplier_sku = ? ORDER BY id ASC",
                (supplier_name, supplier_sku),
            ).fetchall()
            return [SupplierMarketValidationResult(**dict(row)) for row in rows]

    @staticmethod
    def _supplier_backed_from_row(row: sqlite3.Row) -> SupplierBackedProduct:
        data = dict(row)
        for field in (
            "market_price_validated", "platform_fees_validated",
            "return_allowance_validated", "profitable", "auto_approved", "published",
        ):
            data[field] = bool(data[field])
        return SupplierBackedProduct(**data)

    def get_manual_supplier_matches(self, ebay_item_id: str) -> list[dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM manual_supplier_matches WHERE ebay_item_id = ? "
                "ORDER BY id ASC",
                (ebay_item_id,),
            ).fetchall()
            results = [dict(row) for row in rows]
            for result in results:
                if result["direct_ship"] is not None:
                    result["direct_ship"] = bool(result["direct_ship"])
            return results

    def save_draft(self, draft: EBayListingDraft) -> EBayListingDraft:
        now = _now_iso()
        created_at = (
            draft.created_at.isoformat()
            if draft.created_at
            else now
        )
        updated_at = (
            draft.updated_at.isoformat()
            if draft.updated_at
            else now
        )
        reviewed_at = (
            draft.reviewed_at.isoformat()
            if draft.reviewed_at
            else None
        )
        draft_id = draft.draft_id or f"DRAFT-EBAY-{draft.sku}"

        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ebay_listing_drafts (
                    draft_id, candidate_id, title, sku, price,
                    quantity, description, category, category_placeholder,
                    shipping, shipping_placeholder, supplier_reference,
                    expected_profit, expected_margin, status,
                    human_approval_required, reviewed_by, reviewed_at,
                    rejection_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(draft_id) DO UPDATE SET
                    candidate_id=excluded.candidate_id,
                    title=excluded.title,
                    sku=excluded.sku,
                    price=excluded.price,
                    quantity=excluded.quantity,
                    description=excluded.description,
                    category=excluded.category,
                    category_placeholder=excluded.category_placeholder,
                    shipping=excluded.shipping,
                    shipping_placeholder=excluded.shipping_placeholder,
                    supplier_reference=excluded.supplier_reference,
                    expected_profit=excluded.expected_profit,
                    expected_margin=excluded.expected_margin,
                    status=excluded.status,
                    human_approval_required=excluded.human_approval_required,
                    reviewed_by=excluded.reviewed_by,
                    reviewed_at=excluded.reviewed_at,
                    rejection_reason=excluded.rejection_reason,
                    updated_at=excluded.updated_at;
                """,
                (
                    draft_id,
                    draft.candidate_id,
                    draft.title,
                    draft.sku,
                    draft.price,
                    draft.quantity,
                    draft.description,
                    draft.category,
                    draft.category_placeholder,
                    draft.shipping,
                    draft.shipping_placeholder,
                    draft.supplier_reference,
                    draft.expected_profit,
                    draft.expected_margin,
                    draft.status.value,
                    1 if draft.human_approval_required else 0,
                    draft.reviewed_by,
                    reviewed_at,
                    draft.rejection_reason,
                    created_at,
                    updated_at,
                ),
            )

        loaded = self.get_draft(draft_id)
        if loaded is not None:
            return loaded
        draft.draft_id = draft_id
        return draft

    def get_draft(self, draft_id: str) -> Optional[EBayListingDraft]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ebay_listing_drafts WHERE draft_id = ?",
                (draft_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            data["human_approval_required"] = bool(data["human_approval_required"])
            return EBayListingDraft(**data)

    def get_draft_by_candidate_id(self, candidate_id: str) -> Optional[EBayListingDraft]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ebay_listing_drafts WHERE candidate_id = ?",
                (candidate_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            data["human_approval_required"] = bool(data["human_approval_required"])
            return EBayListingDraft(**data)

    def list_drafts(
        self,
        status: Optional[Union[DraftReviewStatus, str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EBayListingDraft]:
        status_val = status.value if isinstance(status, DraftReviewStatus) else status
        query = "SELECT * FROM ebay_listing_drafts"
        params: list = []
        if status_val is not None:
            query += " WHERE status = ?"
            params.append(status_val)
        query += " ORDER BY id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self.get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                data = dict(r)
                data["human_approval_required"] = bool(data["human_approval_required"])
                results.append(EBayListingDraft(**data))
            return results

    def update_draft_status(
        self,
        draft_id: str,
        new_status: Union[DraftReviewStatus, str],
        reviewed_by: Optional[str] = None,
        rejection_reason: Optional[str] = None,
    ) -> EBayListingDraft:
        status_val = (
            new_status.value
            if isinstance(new_status, DraftReviewStatus)
            else str(new_status)
        )
        now = _now_iso()
        reviewed_at = now if status_val == DraftReviewStatus.APPROVED_TO_PUBLISH.value else None

        with self.get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM ebay_listing_drafts WHERE draft_id = ?",
                (draft_id,),
            ).fetchone()
            if not existing:
                raise KeyError(f"Draft '{draft_id}' not found.")

            conn.execute(
                """
                UPDATE ebay_listing_drafts
                SET status = ?,
                    reviewed_by = COALESCE(?, reviewed_by),
                    reviewed_at = COALESCE(?, reviewed_at),
                    rejection_reason = COALESCE(?, rejection_reason),
                    updated_at = ?
                WHERE draft_id = ?
                """,
                (status_val, reviewed_by, reviewed_at, rejection_reason, now, draft_id),
            )

        updated = self.get_draft(draft_id)
        if not updated:
            raise KeyError(f"Draft '{draft_id}' not found after update.")
        return updated

    def save_agent_evaluation(
        self, evaluation: AgentEvaluationRecord
    ) -> AgentEvaluationRecord:
        now = _now_iso()
        created_at = (
            evaluation.created_at.isoformat()
            if evaluation.created_at
            else now
        )
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO agent_evaluations (
                    pipeline_run_id, supplier_sku, supplier_name, agent_role,
                    recommendation, score, confidence, evidence_snapshot,
                    evaluation_details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation.pipeline_run_id,
                    evaluation.supplier_sku,
                    evaluation.supplier_name,
                    evaluation.agent_role.value if hasattr(evaluation.agent_role, "value") else str(evaluation.agent_role),
                    evaluation.recommendation,
                    evaluation.score,
                    evaluation.confidence,
                    json.dumps(evaluation.evidence_snapshot),
                    json.dumps(evaluation.evaluation_details),
                    created_at,
                ),
            )
            saved_id = cursor.lastrowid
        copy_eval = evaluation.model_copy()
        copy_eval.id = saved_id
        if copy_eval.created_at is None:
            copy_eval.created_at = datetime.fromisoformat(created_at)
        return copy_eval

    def list_agent_evaluations(
        self,
        supplier_sku: Optional[str] = None,
        pipeline_run_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[AgentEvaluationRecord]:
        query = "SELECT * FROM agent_evaluations"
        conditions = []
        params = []
        if supplier_sku is not None:
            conditions.append("supplier_sku = ?")
            params.append(supplier_sku)
        if pipeline_run_id is not None:
            conditions.append("pipeline_run_id = ?")
            params.append(pipeline_run_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id ASC LIMIT ?"
        params.append(limit)

        with self.get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                data["evidence_snapshot"] = json.loads(data["evidence_snapshot"])
                data["evaluation_details"] = json.loads(data["evaluation_details"])
                results.append(AgentEvaluationRecord(**data))
            return results

    def record_human_decision(
        self, decision: HumanDecisionRecord
    ) -> HumanDecisionRecord:
        now = _now_iso()
        decided_at = (
            decision.decided_at.isoformat()
            if decision.decided_at
            else now
        )
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO human_decisions (
                    candidate_id, supplier_sku, pipeline_run_id, decision,
                    reviewer_id, reason_category, notes, price_adjustment, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.candidate_id,
                    decision.supplier_sku,
                    decision.pipeline_run_id,
                    decision.decision.value if hasattr(decision.decision, "value") else str(decision.decision),
                    decision.reviewer_id,
                    decision.reason_category,
                    decision.notes,
                    decision.price_adjustment,
                    decided_at,
                ),
            )
            saved_id = cursor.lastrowid
        copy_decision = decision.model_copy()
        copy_decision.id = saved_id
        if copy_decision.decided_at is None:
            copy_decision.decided_at = datetime.fromisoformat(decided_at)
        return copy_decision

    def list_human_decisions(
        self,
        supplier_sku: Optional[str] = None,
        candidate_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[HumanDecisionRecord]:
        query = "SELECT * FROM human_decisions"
        conditions = []
        params = []
        if supplier_sku is not None:
            conditions.append("supplier_sku = ?")
            params.append(supplier_sku)
        if candidate_id is not None:
            conditions.append("candidate_id = ?")
            params.append(candidate_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id ASC LIMIT ?"
        params.append(limit)

        with self.get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [HumanDecisionRecord(**dict(row)) for row in rows]

    def save_realized_outcome(
        self, outcome: RealizedOutcomeRecord
    ) -> RealizedOutcomeRecord:
        now = _now_iso()
        updated_at = (
            outcome.updated_at.isoformat()
            if outcome.updated_at
            else now
        )
        listed_at = outcome.listed_at.isoformat() if outcome.listed_at else None
        first_sale_at = outcome.first_sale_at.isoformat() if outcome.first_sale_at else None

        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO commerce_realized_outcomes (
                    supplier_sku, supplier_name, listing_id, listed_at,
                    first_sale_at, days_to_first_sale, units_sold, actual_sale_price,
                    actual_supplier_cost, actual_platform_fees, realized_net_profit,
                    realized_margin_pct, return_count, return_reasons,
                    supplier_fulfillment_issue, seasonal_window_missed, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(supplier_name, supplier_sku) DO UPDATE SET
                    listing_id=COALESCE(excluded.listing_id, listing_id),
                    listed_at=COALESCE(excluded.listed_at, listed_at),
                    first_sale_at=COALESCE(excluded.first_sale_at, first_sale_at),
                    days_to_first_sale=COALESCE(excluded.days_to_first_sale, days_to_first_sale),
                    units_sold=excluded.units_sold,
                    actual_sale_price=COALESCE(excluded.actual_sale_price, actual_sale_price),
                    actual_supplier_cost=COALESCE(excluded.actual_supplier_cost, actual_supplier_cost),
                    actual_platform_fees=COALESCE(excluded.actual_platform_fees, actual_platform_fees),
                    realized_net_profit=COALESCE(excluded.realized_net_profit, realized_net_profit),
                    realized_margin_pct=COALESCE(excluded.realized_margin_pct, realized_margin_pct),
                    return_count=excluded.return_count,
                    return_reasons=excluded.return_reasons,
                    supplier_fulfillment_issue=COALESCE(excluded.supplier_fulfillment_issue, supplier_fulfillment_issue),
                    seasonal_window_missed=excluded.seasonal_window_missed,
                    updated_at=excluded.updated_at
                """,
                (
                    outcome.supplier_sku,
                    outcome.supplier_name,
                    outcome.listing_id,
                    listed_at,
                    first_sale_at,
                    outcome.days_to_first_sale,
                    outcome.units_sold,
                    outcome.actual_sale_price,
                    outcome.actual_supplier_cost,
                    outcome.actual_platform_fees,
                    outcome.realized_net_profit,
                    outcome.realized_margin_pct,
                    outcome.return_count,
                    json.dumps(outcome.return_reasons),
                    outcome.supplier_fulfillment_issue,
                    1 if outcome.seasonal_window_missed else 0,
                    updated_at,
                ),
            )
            saved_id = cursor.lastrowid
        loaded = self.get_realized_outcome(outcome.supplier_sku, outcome.supplier_name)
        if loaded is not None:
            return loaded
        copy_outcome = outcome.model_copy()
        copy_outcome.id = saved_id
        return copy_outcome

    def get_realized_outcome(
        self, supplier_sku: str, supplier_name: str
    ) -> Optional[RealizedOutcomeRecord]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM commerce_realized_outcomes WHERE supplier_sku = ? AND supplier_name = ?",
                (supplier_sku, supplier_name),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["return_reasons"] = json.loads(data["return_reasons"])
            data["seasonal_window_missed"] = bool(data["seasonal_window_missed"])
            return RealizedOutcomeRecord(**data)

    def list_realized_outcomes(
        self, supplier_sku: Optional[str] = None
    ) -> list[RealizedOutcomeRecord]:
        query = "SELECT * FROM commerce_realized_outcomes"
        params = []
        if supplier_sku is not None:
            query += " WHERE supplier_sku = ?"
            params.append(supplier_sku)
        query += " ORDER BY id ASC"

        with self.get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                data["return_reasons"] = json.loads(data["return_reasons"])
                data["seasonal_window_missed"] = bool(data["seasonal_window_missed"])
                results.append(RealizedOutcomeRecord(**data))
            return results


def init_commerce_database(path: str = "data/commerce.db") -> None:
    """Initializes the commerce SQLite database schema."""
    db = CommerceDatabase(path)
    db.init_db()
