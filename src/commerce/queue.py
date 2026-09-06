from typing import Optional, Union

from src.commerce.database import CommerceDatabase
from src.commerce.schemas import (
    CandidateStatus,
    DraftReviewStatus,
    EBayListingDraft,
    ProductCandidate,
    ProductScoutOpportunity,
    SupplierCheckRecord,
    SupplierProduct,
    clean_ebay_title,
)
from src.commerce.supplier_validator import validate_supplier


class InvalidStatusTransitionError(ValueError):
    """Raised when an invalid queue status transition is attempted."""
    pass


class InvalidDraftStatusTransitionError(ValueError):
    """Raised when an invalid draft human-review status transition is attempted."""
    pass


VALID_DRAFT_STATUS_TRANSITIONS: dict[DraftReviewStatus, set[DraftReviewStatus]] = {
    DraftReviewStatus.DRAFT_CREATED: {
        DraftReviewStatus.READY_FOR_REVIEW,
        DraftReviewStatus.REJECTED,
    },
    DraftReviewStatus.READY_FOR_REVIEW: {
        DraftReviewStatus.APPROVED_TO_PUBLISH,
        DraftReviewStatus.REJECTED,
    },
    DraftReviewStatus.APPROVED_TO_PUBLISH: {
        DraftReviewStatus.REJECTED,
    },
    DraftReviewStatus.REJECTED: {
        DraftReviewStatus.DRAFT_CREATED,
    },
}


VALID_STATUS_TRANSITIONS: dict[CandidateStatus, set[CandidateStatus]] = {
    CandidateStatus.NEW: {
        CandidateStatus.VERIFIED,
        CandidateStatus.REJECTED,
    },
    CandidateStatus.VERIFIED: {
        CandidateStatus.REVIEW,
        CandidateStatus.REJECTED,
    },
    CandidateStatus.REVIEW: {
        CandidateStatus.APPROVED_FOR_LISTING,
        CandidateStatus.REJECTED,
    },
    CandidateStatus.APPROVED_FOR_LISTING: {
        CandidateStatus.REJECTED,
    },
    CandidateStatus.REJECTED: set(),
}


class CandidateQueue:
    """
    Queue and lifecycle manager for commerce product candidates.

    Stages:
      1. NEW: Ingested or scouted candidate awaiting supplier verification.
      2. VERIFIED: Sourcing, supplier type, and unit economics verified.
      3. REVIEW: Candidate submitted for human merchant / critic review.
      4. REJECTED: Candidate rejected at any check stage.
      5. APPROVED_FOR_LISTING: Human-approved candidate ready for listing adapter.
    """

    def __init__(
        self,
        db: Optional[CommerceDatabase] = None,
        db_path: str = "data/commerce.db",
    ):
        if db is not None:
            self.db = db
        else:
            self.db = CommerceDatabase(db_path=db_path)

    def enqueue(self, candidate: ProductCandidate) -> ProductCandidate:
        """Adds a candidate to the queue with initial status NEW."""
        candidate.status = CandidateStatus.NEW
        candidate.rejection_reason = None
        return self.db.save_candidate(candidate)

    def enqueue_from_opportunity(
        self,
        opp: ProductScoutOpportunity,
        candidate_id: Optional[str] = None,
    ) -> ProductCandidate:
        """Converts a scout opportunity into a candidate and enqueues it."""
        candidate = ProductCandidate.from_scout_opportunity(
            opp=opp,
            candidate_id=candidate_id,
        )
        return self.enqueue(candidate)

    def transition(
        self,
        candidate_id: str,
        new_status: Union[CandidateStatus, str],
        reason: Optional[str] = None,
        notes: Optional[str] = None,
        force: bool = False,
    ) -> ProductCandidate:
        """
        Transitions candidate to a new status adhering to allowed state transitions.
        """
        target_status = (
            new_status
            if isinstance(new_status, CandidateStatus)
            else CandidateStatus(new_status)
        )

        current = self.db.get_candidate(candidate_id)
        if not current:
            raise KeyError(f"Candidate '{candidate_id}' not found in queue.")

        current_status = current.status
        if current_status == target_status:
            return current

        if not force:
            allowed = VALID_STATUS_TRANSITIONS.get(current_status, set())
            if target_status not in allowed:
                allowed_str = sorted([s.value for s in allowed])
                raise InvalidStatusTransitionError(
                    f"Cannot transition candidate '{candidate_id}' from {current_status.value} to {target_status.value}. "
                    f"Allowed transitions from {current_status.value}: {allowed_str}"
                )

        rejection_reason = reason if target_status == CandidateStatus.REJECTED else current.rejection_reason
        return self.db.update_candidate_status(
            candidate_id=candidate_id,
            new_status=target_status,
            rejection_reason=rejection_reason,
            notes=notes,
        )

    def verify_supplier(
        self,
        candidate_id: str,
        supplier_product: SupplierProduct,
    ) -> tuple[ProductCandidate, SupplierCheckRecord]:
        """
        Runs supplier validation on the candidate's product source.
        Records check in database, and transitions candidate to VERIFIED or REJECTED.
        """
        candidate = self.db.get_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Candidate '{candidate_id}' not found in queue.")

        validation_result = validate_supplier(supplier_product)
        check_record = SupplierCheckRecord.from_validation_result(
            product=supplier_product,
            result=validation_result,
            candidate_id=candidate_id,
        )
        saved_check = self.db.record_supplier_check(check_record)

        if validation_result.is_valid:
            updated_candidate = self.transition(
                candidate_id=candidate_id,
                new_status=CandidateStatus.VERIFIED,
            )
        else:
            updated_candidate = self.transition(
                candidate_id=candidate_id,
                new_status=CandidateStatus.REJECTED,
                reason=validation_result.reason,
            )

        return updated_candidate, saved_check

    def record_supplier_check(
        self,
        check: SupplierCheckRecord,
        update_candidate: bool = True,
    ) -> tuple[Optional[ProductCandidate], SupplierCheckRecord]:
        """Records an explicit supplier check record and optionally updates candidate status."""
        saved_check = self.db.record_supplier_check(check)
        candidate = None
        if update_candidate and check.candidate_id:
            if check.is_valid:
                candidate = self.transition(
                    candidate_id=check.candidate_id,
                    new_status=CandidateStatus.VERIFIED,
                )
            else:
                candidate = self.transition(
                    candidate_id=check.candidate_id,
                    new_status=CandidateStatus.REJECTED,
                    reason=check.reason,
                )
        return candidate, saved_check

    def submit_for_review(
        self,
        candidate_id: str,
        notes: Optional[str] = None,
    ) -> ProductCandidate:
        """Moves candidate from VERIFIED to REVIEW."""
        return self.transition(
            candidate_id=candidate_id,
            new_status=CandidateStatus.REVIEW,
            notes=notes,
        )

    def approve_for_listing(
        self,
        candidate_id: str,
        reviewer: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ProductCandidate:
        """
        Approves candidate for platform listing.
        Enforces that candidate must be in REVIEW stage.
        """
        approval_note = f"Approved by {reviewer}" if reviewer else "Approved for listing"
        combined_notes = f"{notes} | {approval_note}" if notes else approval_note
        return self.transition(
            candidate_id=candidate_id,
            new_status=CandidateStatus.APPROVED_FOR_LISTING,
            notes=combined_notes,
        )

    def reject(
        self,
        candidate_id: str,
        reason: str,
    ) -> ProductCandidate:
        """Rejects a candidate at any stage with an explanation."""
        return self.transition(
            candidate_id=candidate_id,
            new_status=CandidateStatus.REJECTED,
            reason=reason,
        )

    def reopen(
        self,
        candidate_id: str,
        notes: Optional[str] = None,
    ) -> ProductCandidate:
        """Explicitly reopens a REJECTED candidate back to NEW for re-evaluation."""
        current = self.db.get_candidate(candidate_id)
        if not current:
            raise KeyError(f"Candidate '{candidate_id}' not found in queue.")
        if current.status != CandidateStatus.REJECTED:
            raise InvalidStatusTransitionError(
                f"Candidate '{candidate_id}' is in status '{current.status.value}', only REJECTED candidates can be reopened."
            )
        reopen_note = f"Reopened: {notes}" if notes else "Reopened for re-evaluation"
        return self.transition(
            candidate_id=candidate_id,
            new_status=CandidateStatus.NEW,
            notes=reopen_note,
            force=True,
        )

    def get_candidate(self, candidate_id: str) -> Optional[ProductCandidate]:
        """Fetches candidate by candidate_id."""
        return self.db.get_candidate(candidate_id)

    def get_queue(
        self,
        status: Optional[Union[CandidateStatus, str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProductCandidate]:
        """Lists candidates in a given status or all candidates."""
        return self.db.list_candidates(status=status, limit=limit, offset=offset)

    def get_new(self, limit: int = 100) -> list[ProductCandidate]:
        return self.get_queue(CandidateStatus.NEW, limit=limit)

    def get_verified(self, limit: int = 100) -> list[ProductCandidate]:
        return self.get_queue(CandidateStatus.VERIFIED, limit=limit)

    def get_review(self, limit: int = 100) -> list[ProductCandidate]:
        return self.get_queue(CandidateStatus.REVIEW, limit=limit)

    def get_approved(self, limit: int = 100) -> list[ProductCandidate]:
        return self.get_queue(CandidateStatus.APPROVED_FOR_LISTING, limit=limit)

    def get_rejected(self, limit: int = 100) -> list[ProductCandidate]:
        return self.get_queue(CandidateStatus.REJECTED, limit=limit)

    def get_supplier_checks(
        self,
        candidate_id: Optional[str] = None,
        supplier_id: Optional[str] = None,
    ) -> list[SupplierCheckRecord]:
        return self.db.get_supplier_checks(
            candidate_id=candidate_id,
            supplier_id=supplier_id,
        )

    def count_by_status(self) -> dict[str, int]:
        """Returns candidate counts indexed by status string."""
        candidates = self.db.list_candidates(limit=10000)
        counts = {s.value: 0 for s in CandidateStatus}
        for c in candidates:
            counts[c.status.value] += 1
        return counts

    # -------------------------------------------------------------
    # eBay Listing Draft Management & Human Review Lifecycle
    # -------------------------------------------------------------

    def create_ebay_draft(
        self,
        candidate_id: str,
        quantity: int = 1,
        description: Optional[str] = None,
        category: Optional[str] = None,
        shipping: Optional[str] = None,
    ) -> EBayListingDraft:
        """
        Converts an APPROVED_FOR_LISTING candidate into an eBay listing draft.
        Saves draft in SQLite with initial status DRAFT_CREATED.
        """
        candidate = self.db.get_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Candidate '{candidate_id}' not found in queue.")

        if description is None or shipping is None:
            item_id = candidate.candidate_id.removeprefix("CAND-EBAY-")
            matches = self.db.get_manual_supplier_matches(item_id)
            supplier = next(
                (
                    match for match in reversed(matches)
                    if match.get("verification_status") == "VERIFIED"
                    and match.get("supplier_status") == "VERIFIED_PROFITABLE"
                ),
                None,
            )
            if description is None and supplier:
                facts = [f"Product: {clean_ebay_title(candidate.title)}"]
                if supplier.get("supplier_name"):
                    facts.append(f"Supplier: {supplier['supplier_name']}")
                if supplier.get("sku"):
                    facts.append(f"Supplier SKU: {supplier['sku']}")
                if supplier.get("stock") is not None:
                    facts.append(f"Supplier stock confirmed: {supplier['stock']}")
                description = "\n".join(facts)
            if shipping is None and supplier and supplier.get("shipping") is not None:
                shipping = f"Supplier shipping cost: {supplier['shipping']:.2f}"

        draft = EBayListingDraft.from_candidate(
            candidate=candidate,
            quantity=quantity,
            description=description,
            category=category,
            shipping=shipping,
        )
        return self.db.save_draft(draft)

    def transition_draft(
        self,
        draft_id: str,
        new_status: Union[DraftReviewStatus, str],
        reviewed_by: Optional[str] = None,
        reason: Optional[str] = None,
        force: bool = False,
    ) -> EBayListingDraft:
        """
        Transitions a draft through the human-review lifecycle:
          DRAFT_CREATED -> READY_FOR_REVIEW -> APPROVED_TO_PUBLISH or REJECTED
        """
        target_status = (
            new_status
            if isinstance(new_status, DraftReviewStatus)
            else DraftReviewStatus(new_status)
        )

        current = self.db.get_draft(draft_id)
        if not current:
            raise KeyError(f"Draft '{draft_id}' not found.")

        current_status = current.status
        if current_status == target_status:
            return current

        if not force:
            allowed = VALID_DRAFT_STATUS_TRANSITIONS.get(current_status, set())
            if target_status not in allowed:
                allowed_str = sorted([s.value for s in allowed])
                raise InvalidDraftStatusTransitionError(
                    f"Cannot transition draft '{draft_id}' from {current_status.value} to {target_status.value}. "
                    f"Allowed transitions from {current_status.value}: {allowed_str}"
                )

        if target_status == DraftReviewStatus.APPROVED_TO_PUBLISH and not reviewed_by:
            raise ValueError(
                f"Draft '{draft_id}' approved for publishing must specify reviewed_by (human reviewer identifier)."
            )

        rejection_reason = reason if target_status == DraftReviewStatus.REJECTED else current.rejection_reason
        return self.db.update_draft_status(
            draft_id=draft_id,
            new_status=target_status,
            reviewed_by=reviewed_by,
            rejection_reason=rejection_reason,
        )

    def submit_draft_for_review(self, draft_id: str) -> EBayListingDraft:
        """Transitions draft from DRAFT_CREATED to READY_FOR_REVIEW."""
        return self.transition_draft(
            draft_id=draft_id,
            new_status=DraftReviewStatus.READY_FOR_REVIEW,
        )

    def approve_draft_to_publish(
        self,
        draft_id: str,
        reviewer: str,
    ) -> EBayListingDraft:
        """Approves draft for publishing with human reviewer identification."""
        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer identifier cannot be empty.")
        return self.transition_draft(
            draft_id=draft_id,
            new_status=DraftReviewStatus.APPROVED_TO_PUBLISH,
            reviewed_by=reviewer,
        )

    def reject_draft(
        self,
        draft_id: str,
        reason: str,
    ) -> EBayListingDraft:
        """Rejects draft with a reason."""
        return self.transition_draft(
            draft_id=draft_id,
            new_status=DraftReviewStatus.REJECTED,
            reason=reason,
        )

    def get_draft(self, draft_id: str) -> Optional[EBayListingDraft]:
        return self.db.get_draft(draft_id)

    def get_draft_by_candidate(self, candidate_id: str) -> Optional[EBayListingDraft]:
        return self.db.get_draft_by_candidate_id(candidate_id)

    def list_drafts(
        self,
        status: Optional[Union[DraftReviewStatus, str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EBayListingDraft]:
        return self.db.list_drafts(status=status, limit=limit, offset=offset)

    def get_drafts_created(self, limit: int = 100) -> list[EBayListingDraft]:
        return self.list_drafts(DraftReviewStatus.DRAFT_CREATED, limit=limit)

    def get_drafts_ready_for_review(self, limit: int = 100) -> list[EBayListingDraft]:
        return self.list_drafts(DraftReviewStatus.READY_FOR_REVIEW, limit=limit)

    def get_drafts_approved_to_publish(self, limit: int = 100) -> list[EBayListingDraft]:
        return self.list_drafts(DraftReviewStatus.APPROVED_TO_PUBLISH, limit=limit)

    def get_drafts_rejected(self, limit: int = 100) -> list[EBayListingDraft]:
        return self.list_drafts(DraftReviewStatus.REJECTED, limit=limit)

    def count_drafts_by_status(self) -> dict[str, int]:
        all_drafts = self.db.list_drafts(limit=10000)
        counts = {s.value: 0 for s in DraftReviewStatus}
        for d in all_drafts:
            counts[d.status.value] += 1
        return counts


ProductCandidateQueue = CandidateQueue
CommerceQueue = CandidateQueue
ProductQueue = CandidateQueue
