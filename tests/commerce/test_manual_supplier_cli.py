import json

from src.commerce.database import CommerceDatabase
from src.commerce.manual_supplier_cli import load_shortlist, main, run
from src.commerce.schemas import CandidateStatus, SupplierProfitStatus


def _write_shortlist(path, *, item_id="12345", decision="SHORTLIST"):
    path.write_text(json.dumps({
        "listing": {
            "title": "Manual supplier match item", "item_id": item_id,
            "price": "100.00", "currency": "GBP", "seller": "seller",
            "category": "Home", "item_url": f"https://www.ebay.co.uk/itm/{item_id}",
            "condition": "New", "availability": "IN_STOCK", "end_date": None,
        },
        "seasonal_relevance": 90, "price_attractiveness": 80,
        "competition_density": 80, "signal_quality": 100,
        "data_completeness": 100, "overall_score": 88,
        "decision": decision, "reasons": ["Scored for shortlist."],
    }), encoding="utf-8")


def _answers(*values):
    iterator = iter(values)
    return lambda _prompt: next(iterator)


def test_cli_verifies_persists_and_prints_result(tmp_path, capsys):
    shortlist = tmp_path / "shortlist.json"
    database = tmp_path / "commerce.db"
    _write_shortlist(shortlist)

    exit_code = run(str(shortlist), str(database), input_fn=_answers(
        "Acme Wholesale", "ACME-42", "50", "5", "12", "yes", "verified",
    ))

    assert exit_code == 0
    db = CommerceDatabase(str(database))
    candidate = db.get_candidate("CAND-EBAY-12345")
    assert candidate.status is CandidateStatus.VERIFIED
    assert candidate.supplier_profit_status is SupplierProfitStatus.VERIFIED_PROFITABLE
    assert candidate.estimated_profit == 45.0
    assert len(db.get_supplier_checks(candidate.candidate_id)) == 1
    matches = db.get_manual_supplier_matches("12345")
    assert matches[0]["verification_status"] == "VERIFIED"
    assert matches[0]["expected_margin"] == 0.45

    output = capsys.readouterr().out
    assert "Supplier status: VERIFIED_PROFITABLE" in output
    assert "Expected profit: 45.00" in output
    assert "Margin: 45.00%" in output
    assert "Final outcome:" in output


def test_cli_persists_rejected_verification_without_candidate(tmp_path, capsys):
    shortlist = tmp_path / "shortlist.json"
    database = tmp_path / "commerce.db"
    _write_shortlist(shortlist)

    run(str(shortlist), str(database), input_fn=_answers(
        "Acme Wholesale", "ACME-42", "50", "5", "12", "no", "rejected",
    ))

    db = CommerceDatabase(str(database))
    assert db.get_candidate("CAND-EBAY-12345") is None
    match = db.get_manual_supplier_matches("12345")[0]
    assert match["supplier_status"] == "SUPPLIER_REJECTED"
    assert match["expected_profit"] is None
    output = capsys.readouterr().out
    assert "Expected profit: N/A" in output
    assert "Margin: N/A" in output


def test_cli_arguments_run_supplier_verification_without_prompts(tmp_path, capsys):
    shortlist = tmp_path / "shortlist.json"
    database = tmp_path / "commerce.db"
    _write_shortlist(shortlist)

    exit_code = main([
        str(shortlist), "--db", str(database),
        "--supplier-name", "Go Dropship",
        "--supplier-sku", "GO-42",
        "--supplier-cost", "50",
        "--shipping-cost", "5",
        "--stock-confirmed", "12",
        "--direct-ship", "yes",
        "--verification-status", "verified",
    ])

    assert exit_code == 0
    match = CommerceDatabase(str(database)).get_manual_supplier_matches("12345")[0]
    assert match["supplier_name"] == "Go Dropship"
    assert match["sku"] == "GO-42"
    assert match["cost"] == 50.0
    assert match["shipping"] == 5.0
    assert match["stock"] == 12
    assert match["direct_ship"] is True
    assert match["verification_status"] == "VERIFIED"
    assert "Supplier status: VERIFIED_PROFITABLE" in capsys.readouterr().out


def test_cli_arguments_only_replace_corresponding_prompts(tmp_path):
    shortlist = tmp_path / "shortlist.json"
    database = tmp_path / "commerce.db"
    _write_shortlist(shortlist)

    run(
        str(shortlist), str(database),
        supplier_name="Go Dropship",
        supplier_cost=50,
        stock_confirmed=12,
        verification_status="verified",
        input_fn=_answers("GO-42", "5", "yes"),
    )

    match = CommerceDatabase(str(database)).get_manual_supplier_matches("12345")[0]
    assert match["supplier_name"] == "Go Dropship"
    assert match["sku"] == "GO-42"
    assert match["shipping"] == 5.0
    assert match["direct_ship"] is True


def test_cli_selects_one_candidate_from_a_shortlist(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    shortlist = tmp_path / "shortlist.json"
    database = tmp_path / "commerce.db"
    _write_shortlist(first, item_id="111")
    _write_shortlist(second, item_id="222")
    shortlist.write_text(json.dumps([
        json.loads(first.read_text(encoding="utf-8")),
        json.loads(second.read_text(encoding="utf-8")),
    ]), encoding="utf-8")

    run(str(shortlist), str(database), input_fn=_answers(
        "2", "Acme Wholesale", "ACME-42", "50", "5", "12", "yes", "verified",
    ))

    db = CommerceDatabase(str(database))
    assert db.get_candidate("CAND-EBAY-111") is None
    assert db.get_candidate("CAND-EBAY-222") is not None


def test_load_shortlist_rejects_non_shortlisted_candidate(tmp_path):
    shortlist = tmp_path / "watch.json"
    _write_shortlist(shortlist, decision="WATCH")

    try:
        load_shortlist(str(shortlist))
    except ValueError as exc:
        assert "SHORTLIST" in str(exc)
    else:
        raise AssertionError("WATCH candidate should not load")
