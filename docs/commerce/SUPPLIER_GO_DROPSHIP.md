# Go Dropship Supplier

Status: Active

## Current Behaviour

- Public product discovery
- Cost capture
- Stock capture
- Source URL capture
- Product image extraction
- Blind shipping supported
- UK return route supported
- Supplier order placement remains manual

## Adapter

`src/commerce/adapters/godropship.py`

## Normalized Identity

- supplier_id: go_dropship
- supplier_name: Go Dropship

## Safety

Supplier stock and price must be rechecked before replenishing a marketplace listing.

No supplier order is placed automatically.
