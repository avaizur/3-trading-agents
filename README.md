# 3 Trading Agents

Phase 1: paper trading only, deterministic risk controls, human approval required.

Run tests:

```bash
python -m pytest -q
```

Run local manual supplier verification against a JSON file containing one or
more serialized `ScoredMarketOpportunity` records:

```bash
python -m src.commerce.manual_supplier_cli shortlist.json --db data/commerce.db
```

This command only records verification results. It does not publish listings or
place supplier orders.
