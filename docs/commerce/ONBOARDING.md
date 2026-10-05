# Commerce Onboarding

This project uses reusable supplier and marketplace adapters.

## New Supplier

To onboard a new supplier:

1. Create a supplier adapter in:
   `src/commerce/adapters/`

2. Implement:
   - get_product(sku)
   - check_inventory(sku)
   - discovery/import logic if supported

3. Normalize supplier data into:
   - supplier name
   - SKU
   - product title
   - cost
   - stock
   - source URL
   - images/specifications where available

4. Register the adapter in:
   `src/commerce/adapters/registry.py`

5. Add configuration in:
   `src/commerce/adapters/config.py`

6. Add tests.

7. Supplier order placement must remain manual unless policy is deliberately changed.

## New Marketplace

To onboard a new marketplace:

1. Create a marketplace adapter in:
   `src/commerce/adapters/`

2. Implement:
   - create_listing
   - publish_listing
   - estimate_fees
   - connection/auth checks
   - marketplace taxonomy/attributes
   - listing validation

3. Register the platform in:
   `src/commerce/schemas.py`

4. Register the adapter in:
   `src/commerce/adapters/registry.py`

5. Add configuration in:
   `src/commerce/adapters/config.py`

6. Store credentials in AWS Secrets Manager.

7. Add marketplace-specific tests.

8. Keep human approval mandatory before publish.

## Shared Safety Rules

- Minimum target margin: 20%
- Cheap market validation before expensive/deep work
- Human approval before listing preparation
- Second human approval before publication
- No automatic supplier ordering
- No secrets in Git
- No blind copying of one marketplace listing into another
- Each marketplace must validate its own category, attributes, fees, and policies

## Current Status

### Suppliers
- Go Dropship: active
- Future suppliers: adapter + config onboarding

### Marketplaces
- eBay: active
- TikTok Shop: framework ready, awaiting seller app/API authorization
- Amazon: framework ready, awaiting SP-API onboarding
- Etsy: framework ready, awaiting OAuth/API onboarding
