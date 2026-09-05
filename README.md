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

Create that file from read-only eBay Browse research and the existing
opportunity scorer (requires `EBAY_ACCESS_TOKEN`):

```bash
python -m src.commerce.shortlist_cli --top 10 --output shortlist.json
```

The exporter makes GET-only marketplace searches and writes only the requested
local JSON file. It includes complete scored listing records for the manual
supplier-verification CLI and never publishes or orders anything.

This command only records verification results. It does not publish listings or
place supplier orders.
