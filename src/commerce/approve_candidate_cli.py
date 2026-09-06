"""Approve one reviewed commerce candidate for listing."""

import argparse
from typing import Sequence

from src.commerce.queue import CandidateQueue, InvalidStatusTransitionError
from src.commerce.schemas import CandidateStatus


def approve_candidate(
    candidate_id: str,
    db_path: str = "data/commerce.db",
) -> tuple[CandidateStatus, CandidateStatus]:
    """Approve an explicitly selected REVIEW candidate using queue lifecycle rules."""
    queue = CandidateQueue(db_path=db_path)
    candidate = queue.get_candidate(candidate_id)
    if candidate is None:
        raise KeyError(f"Candidate '{candidate_id}' not found in queue.")
    if candidate.status is not CandidateStatus.REVIEW:
        raise InvalidStatusTransitionError(
            f"Cannot approve candidate '{candidate_id}' from {candidate.status.value}; "
            "candidate must be in REVIEW."
        )

    before = candidate.status
    approved = queue.approve_for_listing(candidate_id)
    return before, approved.status


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-id",
        required=True,
        help="Exact commerce candidate ID to approve",
    )
    parser.add_argument("--db", default="data/commerce.db", help="SQLite database path")
    args = parser.parse_args(argv)

    try:
        before, after = approve_candidate(args.candidate_id, args.db)
    except (KeyError, OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"Before status: {before.value}")
    print(f"After status: {after.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
