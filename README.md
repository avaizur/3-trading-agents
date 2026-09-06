# 3 Trading Agents

Phase 1: paper trading only, deterministic risk controls, human approval required.

Run tests:

```bash
python -m pytest -q
```

While eBay Developer API access is unavailable, create `manual-candidates.json`
as a JSON array (or `{ "candidates": [...] }`) containing 5-10 manually
researched eBay listings. Each listing uses these fields:

```json
{
  "title": "Product title",
  "item_id": "1234567890",
  "price": "29.99",
  "currency": "GBP",
  "seller": "seller-name",
  "category": "Home & Garden",
  "item_url": "https://www.ebay.co.uk/itm/1234567890",
  "condition": "New",
  "availability": "IN_STOCK",
  "end_date": null
}
```

Score that local research with the existing opportunity scorer, without any
live API calls:

```bash
python -m src.commerce.manual_shortlist_cli manual-candidates.json \
  --output shortlist.json
```

The input must contain 5-10 unique eBay items. Only candidates receiving the
existing `SHORTLIST` decision are written to `shortlist.json`. To reproduce a
past seasonal window, pass `--as-of YYYY-MM-DD`.

Run local manual supplier verification against a JSON file containing one or
more serialized `ScoredMarketOpportunity` records:

```bash
python -m src.commerce.manual_supplier_cli shortlist.json --db data/commerce.db
```

Known supplier data can be supplied non-interactively; omit any option to be
prompted for just that value:

```bash
python -m src.commerce.manual_supplier_cli shortlist.json \
  --db data/commerce.db \
  --supplier-name "Go Dropship" \
  --supplier-sku "SUPPLIER-SKU" \
  --supplier-cost 10.00 \
  --shipping-cost 2.99 \
  --stock-confirmed 10 \
  --direct-ship yes \
  --verification-status VERIFIED
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

After a `VERIFIED_PROFITABLE` candidate has completed the existing human review
and reached `APPROVED_FOR_LISTING`, create and persist an eBay-ready local draft:

```bash
python -m src.commerce.ebay_listing_draft_cli --db data/commerce.db
```

Use `--candidate-id CAND-EBAY-...` to select a specific eligible candidate. The
command prints the draft as JSON and never calls or publishes to eBay.
