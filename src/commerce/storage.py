"""Storage contract for the commerce pipeline.

SQLite remains the development/test implementation.
Serverless production storage can implement the same interface later.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol


class CommerceStore(Protocol):
    """Persistence operations required by the commerce pipeline."""

    # Candidates
    def save_candidate(self, candidate: Any) -> Any: ...
    def get_candidate(self, candidate_id: str) -> Optional[Any]: ...
    def list_candidates(
        self,
        status: Any = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]: ...
    def update_candidate_status(
        self,
        candidate_id: str,
        status: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any: ...

    # Supplier checks
    def record_supplier_check(self, check: Any) -> Any: ...
    def get_supplier_checks(
        self,
        candidate_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> list[Any]: ...

    # Supplier matching / catalogue
    def get_manual_supplier_matches(self, ebay_item_id: str) -> list[dict]: ...
    def get_supplier_backed_product(
        self,
        supplier_name: str,
        supplier_sku: str,
    ) -> Optional[Any]: ...
    def list_supplier_backed_products(self) -> list[Any]: ...

    # Supplier policy
    def get_supplier_policy_rules(self, supplier_id: str) -> Optional[Any]: ...

    # Drafts
    def save_draft(self, draft: Any) -> Any: ...
    def get_draft(self, draft_id: str) -> Optional[Any]: ...
    def get_draft_by_candidate_id(self, candidate_id: str) -> Optional[Any]: ...
    def list_drafts(
        self,
        status: Any = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]: ...
    def update_draft_status(
        self,
        draft_id: str,
        status: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any: ...

    # Agent history
    def save_agent_evaluation(
        self,
        evaluation: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any: ...

    def list_agent_evaluations(
        self,
        supplier_sku: Any = None,
        pipeline_run_id: Any = None,
        limit: int = 100,
    ) -> list[Any]: ...
