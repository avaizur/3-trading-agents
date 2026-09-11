"""Approve one reviewed commerce candidate for listing."""

import argparse
from typing import Sequence

from src.commerce.queue import CandidateQueue, InvalidStatusTransitionError
from src.commerce.schemas import CandidateStatus


def resolve_candidate_id(queue: CandidateQueue, candidate_id: str | None, sku: str | None) -> str:
    if candidate_id is not None:
        return candidate_id
    matches = queue.db.get_candidates_by_sku(sku)
    if not matches:
        raise KeyError(f"Candidate with SKU '{sku}' not found in queue.")
    if len(matches) > 1:
        raise ValueError(f"SKU '{sku}' is ambiguous; use --candidate-id.")
    return matches[0].candidate_id


def approve_candidate(
    candidate_id: str | None = None,
    db_path: str = "data/commerce.db",
    *,
    sku: str | None = None,
    reviewer: str | None = None,
) -> tuple[CandidateStatus, CandidateStatus]:
    """Approve an explicitly selected REVIEW candidate using queue lifecycle rules."""
    queue = CandidateQueue(db_path=db_path)
    candidate_id = resolve_candidate_id(queue, candidate_id, sku)
    candidate = queue.get_candidate(candidate_id)
    if candidate is None:
        raise KeyError(f"Candidate '{candidate_id}' not found in queue.")
    if candidate.status is not CandidateStatus.REVIEW:
        raise InvalidStatusTransitionError(
            f"Cannot approve candidate '{candidate_id}' from {candidate.status.value}; "
            "candidate must be in REVIEW."
        )

    before = candidate.status
    approved = queue.approve_for_listing(candidate_id, reviewer=reviewer)
    return before, approved.status


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--candidate-id", help="Exact commerce candidate ID to approve")
    target.add_argument("--sku", help="Exact unique supplier SKU to approve")
    parser.add_argument("--reviewer", help="Human reviewer identifier")
    parser.add_argument("--db", default="data/commerce.db", help="SQLite database path")
    args = parser.parse_args(argv)

    try:
        before, after = approve_candidate(
            args.candidate_id, args.db, sku=args.sku, reviewer=args.reviewer
        )
    except (KeyError, OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"Before status: {before.value}")
    print(f"After status: {after.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
