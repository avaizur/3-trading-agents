import json
from datetime import date

import pytest

from src.commerce.manual_shortlist_cli import (
    load_manual_candidates,
    score_manual_candidates,
)
from src.commerce.database import CommerceDatabase
from src.commerce.manual_supplier_cli import load_shortlist, run
from src.commerce.schemas import CandidateStatus, SupplierProfitStatus


def _candidate(index):
    return {
        "title": f"Halloween pumpkin decor lights {index}",
        "item_id": str(index),
        "price": str(10 + index),
        "currency": "GBP",
        "seller": f"seller-{index}",
        "category": f"Halloween Decorations {index}",
        "item_url": f"https://www.ebay.co.uk/itm/{index}",
        "condition": "New",
        "availability": "IN_STOCK",
        "end_date": "2026-10-20T12:00:00+00:00",
    }


def _write(path, rows):
    path.write_text(json.dumps(rows), encoding="utf-8")


def _answers(*values):
    iterator = iter(values)
    return lambda _prompt: next(iterator)


def test_manual_candidates_use_existing_scorer_and_supplier_input_format(tmp_path):
    source = tmp_path / "manual.json"
    output = tmp_path / "shortlist.json"
    _write(source, {"candidates": [_candidate(index) for index in range(5)]})

    count = score_manual_candidates(source, output, as_of=date(2026, 9, 5))

    raw = json.loads(output.read_text(encoding="utf-8"))
    supplier_ready = load_shortlist(str(output))
    assert count == len(raw) == len(supplier_ready) == 5
    assert all(row["decision"] == "SHORTLIST" for row in raw)
    assert all(len(row["reasons"]) == 6 for row in raw)
    assert [row["overall_score"] for row in raw] == sorted(
        (row["overall_score"] for row in raw), reverse=True
    )


def test_one_manual_product_runs_through_existing_supplier_profit_flow(tmp_path):
    source = tmp_path / "manual.json"
    shortlist = tmp_path / "shortlist.json"
    database = tmp_path / "commerce.db"
    _write(source, [_candidate(index) for index in range(5)])
    score_manual_candidates(source, shortlist, as_of=date(2026, 9, 5))

    run(str(shortlist), str(database), input_fn=_answers(
        "1", "Acme Wholesale", "ACME-1", "5", "1", "10", "yes", "verified",
    ))

    db = CommerceDatabase(str(database))
    candidates = db.list_candidates()
    assert len(candidates) == 1
    assert candidates[0].status is CandidateStatus.VERIFIED
    assert candidates[0].supplier_profit_status is SupplierProfitStatus.VERIFIED_PROFITABLE
    assert db.get_manual_supplier_matches(candidates[0].candidate_id.removeprefix("CAND-EBAY-"))


@pytest.mark.parametrize("count", [4, 11])
def test_manual_candidates_require_five_to_ten_records(tmp_path, count):
    source = tmp_path / "manual.json"
    _write(source, [_candidate(index) for index in range(count)])

    with pytest.raises(ValueError, match="5 to 10"):
        load_manual_candidates(source)


def test_manual_candidates_reject_non_ebay_urls(tmp_path):
    source = tmp_path / "manual.json"
    rows = [_candidate(index) for index in range(5)]
    rows[0]["item_url"] = "https://amazon.example/item/0"
    _write(source, rows)

    with pytest.raises(ValueError, match="eBay"):
        load_manual_candidates(source)


def test_manual_candidates_reject_duplicate_item_ids(tmp_path):
    source = tmp_path / "manual.json"
    rows = [_candidate(index) for index in range(5)]
    rows[-1]["item_id"] = rows[0]["item_id"]
    _write(source, rows)

    with pytest.raises(ValueError, match="unique"):
        load_manual_candidates(source)
