import pytest

from src.commerce.approve_candidate_cli import main
from src.commerce.database import CommerceDatabase
from src.commerce.schemas import CandidateStatus, ProductCandidate


def _save_candidate(db_path, status):
    db = CommerceDatabase(str(db_path))
    return db.save_candidate(
        ProductCandidate(
            candidate_id="CAND-EBAY-APPROVE-1",
            sku="SKU-APPROVE-1",
            title="Candidate awaiting approval",
            supplier_id="SUPPLIER-1",
            supplier_cost=10.0,
            target_price=25.0,
            status=status,
        )
    )


def test_command_approves_explicit_review_candidate_and_prints_statuses(
    tmp_path, capsys
):
    db_path = tmp_path / "commerce.db"
    candidate = _save_candidate(db_path, CandidateStatus.REVIEW)

    result = main(
        ["--candidate-id", candidate.candidate_id, "--db", str(db_path)]
    )

    assert result == 0
    assert capsys.readouterr().out.splitlines() == [
        "Before status: REVIEW",
        "After status: APPROVED_FOR_LISTING",
    ]
    saved = CommerceDatabase(str(db_path)).get_candidate(candidate.candidate_id)
    assert saved.status is CandidateStatus.APPROVED_FOR_LISTING


@pytest.mark.parametrize(
    "status",
    [
        CandidateStatus.NEW,
        CandidateStatus.VERIFIED,
        CandidateStatus.APPROVED_FOR_LISTING,
        CandidateStatus.REJECTED,
    ],
)
def test_command_rejects_every_status_except_review(tmp_path, capsys, status):
    db_path = tmp_path / "commerce.db"
    candidate = _save_candidate(db_path, status)

    with pytest.raises(SystemExit) as exc_info:
        main(["--candidate-id", candidate.candidate_id, "--db", str(db_path)])

    assert exc_info.value.code == 2
    assert "candidate must be in REVIEW" in capsys.readouterr().err
    saved = CommerceDatabase(str(db_path)).get_candidate(candidate.candidate_id)
    assert saved.status is status


def test_command_requires_explicit_candidate_id(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--db", str(tmp_path / "commerce.db")])

    assert exc_info.value.code == 2
    assert "--candidate-id" in capsys.readouterr().err
