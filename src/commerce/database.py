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
    SupplierCheckRecord,
    SupplierType,
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

    def close(self) -> None:
        if self._shared_conn is not None:
            self._shared_conn.close()
            self._shared_conn = None

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


def init_commerce_database(path: str = "data/commerce.db") -> None:
    """Initializes the commerce SQLite database schema."""
    db = CommerceDatabase(path)
    db.init_db()
