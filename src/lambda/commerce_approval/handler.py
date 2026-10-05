"""Two-stage serverless human approval for commerce listings.

Stage 1:
GET review page
POST approve -> candidate APPROVED_FOR_LISTING, prepare eBay offer,
               create listing draft, move draft to READY_FOR_REVIEW

Stage 2:
POST publish -> draft APPROVED_TO_PUBLISH, publish eBay offer,
               persist LIVE_LISTING record

Safety:
- GET never changes state
- first approval never publishes
- publish requires a second explicit human POST
- duplicate live SKU publishing is blocked
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import parse_qs

import boto3
from botocore.exceptions import ClientError

from src.commerce.dynamo_storage import DynamoCommerceStore
from src.commerce.ebay_inventory_service import (
    load_access_token,
    prepare_offer,
    publish_offer,
)
from src.commerce.listing_facts_store import ListingFactsStore
from src.commerce.prepare_listing_cli import build_description
from src.commerce.queue import CandidateQueue
from src.commerce.schemas import CandidateStatus


TABLE_NAME = os.environ["COMMERCE_TABLE_NAME"]
REGION = os.environ.get("AWS_REGION", "eu-west-2")

dynamodb = boto3.resource(
    "dynamodb",
    region_name=REGION,
)

table = dynamodb.Table(TABLE_NAME)

store = DynamoCommerceStore(
    table_name=TABLE_NAME,
    region_name=REGION,
    dynamodb_resource=dynamodb,
)

facts_store = ListingFactsStore(
    table_name=TABLE_NAME,
    region_name=REGION,
    dynamodb_resource=dynamodb,
)

queue = CandidateQueue(db=store)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _response(status_code: int, body: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        "body": body,
    }


def _token_hash(token: str) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def _get_approval(approval_id: str) -> dict | None:
    response = table.get_item(
        Key={
            "PK": f"APPROVAL#{approval_id}",
            "SK": "META",
        }
    )
    return response.get("Item")


def _validate_approval(
    approval_id: str,
    token: str,
    expected_status: str,
) -> dict:
    if not approval_id or not token:
        raise ValueError(
            "Approval ID and token are required."
        )

    approval = _get_approval(approval_id)

    if approval is None:
        raise ValueError(
            "Approval request was not found."
        )

    expected_hash = str(
        approval.get("token_hash", "")
    )

    supplied_hash = _token_hash(token)

    if (
        not expected_hash
        or not hmac.compare_digest(
            supplied_hash,
            expected_hash,
        )
    ):
        raise ValueError(
            "Approval token is invalid."
        )

    status = str(
        approval.get("status", "")
    )

    if status != expected_status:
        raise ValueError(
            f"Approval request is already {status or 'closed'}."
        )

    expires_at = approval.get("expires_at")

    if expires_at:
        expires = datetime.fromisoformat(
            str(expires_at)
        )

        if expires.tzinfo is None:
            expires = expires.replace(
                tzinfo=timezone.utc
            )

        if datetime.now(timezone.utc) > expires:
            raise ValueError(
                "Approval request has expired."
            )

    return approval


def _get_live_listing(sku: str) -> dict | None:
    response = table.get_item(
        Key={
            "PK": f"LIVE_LISTING#EBAY#{sku}",
            "SK": "META",
        }
    )
    return response.get("Item")


def _save_live_listing(
    *,
    sku: str,
    candidate_id: str,
    draft_id: str,
    offer_id: str,
    listing_id: str,
) -> None:
    table.put_item(
        Item={
            "PK": f"LIVE_LISTING#EBAY#{sku}",
            "SK": "META",
            "entity_type": "EBAY_LIVE_LISTING",
            "sku": sku,
            "candidate_id": candidate_id,
            "draft_id": draft_id,
            "offer_id": offer_id,
            "listing_id": listing_id,
            "marketplace_id": "EBAY_GB",
            "status": "LIVE",
            "published_at": _now(),
        },
        ConditionExpression=(
            "attribute_not_exists(PK)"
        ),
    )


def _transition_approval(
    *,
    approval_id: str,
    from_status: str,
    to_status: str,
    values: dict | None = None,
) -> None:
    values = values or {}

    names = {
        "#status": "status",
    }

    expression_values = {
        ":from_status": from_status,
        ":to_status": to_status,
        ":now": _now(),
    }

    sets = [
        "#status = :to_status",
        "updated_at = :now",
    ]

    for index, (name, value) in enumerate(
        values.items()
    ):
        name_key = f"#n{index}"
        value_key = f":v{index}"

        names[name_key] = name
        expression_values[value_key] = value
        sets.append(
            f"{name_key} = {value_key}"
        )

    try:
        table.update_item(
            Key={
                "PK": f"APPROVAL#{approval_id}",
                "SK": "META",
            },
            UpdateExpression=(
                "SET " + ", ".join(sets)
            ),
            ConditionExpression=(
                "#status = :from_status"
            ),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=(
                expression_values
            ),
        )

    except ClientError as exc:
        code = (
            exc.response
            .get("Error", {})
            .get("Code")
        )

        if code == (
            "ConditionalCheckFailedException"
        ):
            raise ValueError(
                "Approval request has already been used."
            ) from None

        raise


def _parse_form(event: dict) -> dict[str, str]:
    body = event.get("body") or ""

    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except Exception as exc:
            raise ValueError(
                "Invalid encoded request body."
            ) from exc

    parsed = parse_qs(
        body,
        keep_blank_values=True,
    )

    return {
        key: values[0]
        for key, values in parsed.items()
        if values
    }


def _review_page(
    *,
    approval_id: str,
    token: str,
    candidate,
) -> str:
    profit = (
        "N/A"
        if candidate.estimated_profit is None
        else f"£{candidate.estimated_profit:.2f}"
    )

    margin = (
        "N/A"
        if candidate.estimated_margin_pct is None
        else (
            f"{candidate.estimated_margin_pct * 100:.2f}%"
        )
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">
<title>3 Trading Agents Approval</title>
<style>
body {{
  font-family: Arial, sans-serif;
  max-width: 720px;
  margin: 40px auto;
  padding: 0 20px;
}}
.card {{
  border: 1px solid #ddd;
  border-radius: 14px;
  padding: 24px;
}}
button {{
  padding: 12px 18px;
  margin: 8px 8px 0 0;
  font-size: 16px;
}}
.approve {{
  background: #111;
  color: white;
}}
.warning {{
  background: #f4f4f4;
  padding: 12px;
  margin-top: 18px;
}}
</style>
</head>
<body>
<div class="card">

<h2>Product approval</h2>
<h3>{html.escape(candidate.title)}</h3>

<p>SKU: {html.escape(candidate.sku)}</p>
<p>Supplier: {html.escape(candidate.supplier_id)}</p>
<p>Target price: £{candidate.target_price:.2f}</p>
<p>Supplier cost: £{candidate.supplier_cost:.2f}</p>
<p>Expected profit: {profit}</p>
<p>Expected margin: {margin}</p>

<div class="warning">
This first approval only prepares the eBay listing.
It does <strong>not</strong> publish it.
</div>

<form method="post">
<input type="hidden"
       name="approval_id"
       value="{html.escape(approval_id)}">

<input type="hidden"
       name="token"
       value="{html.escape(token)}">

<button class="approve"
        type="submit"
        name="action"
        value="prepare">
Approve Listing Preparation
</button>

<button type="submit"
        name="action"
        value="reject">
Reject
</button>
</form>

</div>
</body>
</html>"""


def _publish_page(
    *,
    approval_id: str,
    token: str,
    candidate,
    offer_id: str,
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">
<title>Final eBay Publish Approval</title>
<style>
body {{
  font-family: Arial, sans-serif;
  max-width: 720px;
  margin: 40px auto;
  padding: 0 20px;
}}
.card {{
  border: 1px solid #ddd;
  border-radius: 14px;
  padding: 24px;
}}
.publish {{
  background: #111;
  color: white;
  padding: 14px 20px;
  font-size: 17px;
}}
.warning {{
  background: #fff3cd;
  padding: 14px;
  margin: 18px 0;
}}
</style>
</head>
<body>
<div class="card">

<h2>Final publish approval</h2>

<h3>{html.escape(candidate.title)}</h3>

<p>SKU: {html.escape(candidate.sku)}</p>
<p>Price: £{candidate.target_price:.2f}</p>
<p>eBay Offer ID: {html.escape(offer_id)}</p>

<div class="warning">
The listing has been prepared but remains
<strong>UNPUBLISHED</strong>.

Pressing the button below will publish it live on eBay.
</div>

<form method="post">
<input type="hidden"
       name="approval_id"
       value="{html.escape(approval_id)}">

<input type="hidden"
       name="token"
       value="{html.escape(token)}">

<button class="publish"
        type="submit"
        name="action"
        value="publish">
Publish to eBay
</button>
</form>

</div>
</body>
</html>"""


def lambda_handler(event, context):
    method = str(
        (
            event.get("requestContext", {})
            .get("http", {})
            .get("method", "GET")
        )
    ).upper()

    try:
        if method == "GET":
            params = (
                event.get(
                    "queryStringParameters"
                )
                or {}
            )

            approval_id = str(
                params.get("approval_id", "")
            )
            token = str(
                params.get("token", "")
            )

            approval = _validate_approval(
                approval_id,
                token,
                "PENDING",
            )

            candidate = store.get_candidate(
                str(approval["candidate_id"])
            )

            if candidate is None:
                return _response(
                    404,
                    "<h2>Candidate not found.</h2>",
                )

            if (
                candidate.status
                is not CandidateStatus.REVIEW
            ):
                return _response(
                    409,
                    "<h2>Candidate is no longer awaiting review.</h2>",
                )

            return _response(
                200,
                _review_page(
                    approval_id=approval_id,
                    token=token,
                    candidate=candidate,
                ),
            )

        if method != "POST":
            return _response(
                405,
                "<h2>Method not allowed.</h2>",
            )

        form = _parse_form(event)

        approval_id = form.get(
            "approval_id",
            "",
        )
        token = form.get(
            "token",
            "",
        )
        action = form.get(
            "action",
            "",
        ).lower()

        if action == "prepare":
            approval = _validate_approval(
                approval_id,
                token,
                "PENDING",
            )

            candidate_id = str(
                approval["candidate_id"]
            )

            candidate = store.get_candidate(
                candidate_id
            )

            if candidate is None:
                return _response(
                    404,
                    "<h2>Candidate not found.</h2>",
                )

            if (
                candidate.status
                is not CandidateStatus.REVIEW
            ):
                raise ValueError(
                    "Candidate is no longer awaiting review."
                )

            if _get_live_listing(candidate.sku):
                raise ValueError(
                    "This SKU already has a recorded live eBay listing."
                )

            facts = facts_store.get(
                sku=candidate.sku
            )

            if facts is None:
                raise ValueError(
                    "Verified eBay listing facts are missing."
                )

            approved_candidate = (
                queue.approve_for_listing(
                    candidate_id=candidate_id,
                    reviewer="secure-web-approval",
                    notes=(
                        "Approved through serverless "
                        "candidate approval page."
                    ),
                )
            )

            ebay_token = load_access_token(
                region=REGION
            )

            prepared = prepare_offer(
                sku=approved_candidate.sku,
                price=approved_candidate.target_price,
                facts=facts,
                token=ebay_token,
                quantity=1,
            )

            existing_draft = (
                store.get_draft_by_candidate_id(
                    candidate_id
                )
            )

            if existing_draft is None:
                draft = queue.create_ebay_draft(
                    candidate_id=candidate_id,
                    quantity=1,
                    description=build_description(
                        facts
                    ),
                    category=(
                        facts.get("ebay_category")
                        or str(
                            facts[
                                "ebay_category_id"
                            ]
                        )
                    ),
                    shipping=(
                        facts.get("shipping")
                        or "Verified supplier shipping"
                    ),
                )

                draft = (
                    queue.submit_draft_for_review(
                        draft.draft_id
                    )
                )
            else:
                draft = existing_draft

            publish_token = (
                secrets.token_urlsafe(32)
            )

            _transition_approval(
                approval_id=approval_id,
                from_status="PENDING",
                to_status="PENDING_PUBLISH",
                values={
                    "token_hash": _token_hash(
                        publish_token
                    ),
                    "offer_id": prepared[
                        "offer_id"
                    ],
                    "draft_id": draft.draft_id,
                    "sku": approved_candidate.sku,
                    "prepared_at": _now(),
                },
            )

            return _response(
                200,
                _publish_page(
                    approval_id=approval_id,
                    token=publish_token,
                    candidate=approved_candidate,
                    offer_id=str(
                        prepared["offer_id"]
                    ),
                ),
            )

        if action == "reject":
            approval = _validate_approval(
                approval_id,
                token,
                "PENDING",
            )

            candidate_id = str(
                approval["candidate_id"]
            )

            queue.reject(
                candidate_id=candidate_id,
                reason=(
                    "Rejected through "
                    "serverless approval page."
                ),
            )

            _transition_approval(
                approval_id=approval_id,
                from_status="PENDING",
                to_status="REJECTED",
            )

            return _response(
                200,
                "<h2>Product rejected.</h2>",
            )

        if action == "publish":
            approval = _validate_approval(
                approval_id,
                token,
                "PENDING_PUBLISH",
            )

            candidate_id = str(
                approval["candidate_id"]
            )
            sku = str(
                approval["sku"]
            )
            offer_id = str(
                approval["offer_id"]
            )
            draft_id = str(
                approval["draft_id"]
            )

            if _get_live_listing(sku):
                raise ValueError(
                    "This SKU is already recorded as LIVE."
                )

            draft = store.get_draft(
                draft_id
            )

            if draft is None:
                raise ValueError(
                    "Listing draft was not found."
                )

            queue.approve_draft_to_publish(
                draft_id=draft_id,
                reviewer="secure-web-publish",
            )

            ebay_token = load_access_token(
                region=REGION
            )

            published = publish_offer(
                offer_id=offer_id,
                token=ebay_token,
            )

            listing_id = str(
                published["listing_id"]
            )

            _save_live_listing(
                sku=sku,
                candidate_id=candidate_id,
                draft_id=draft_id,
                offer_id=offer_id,
                listing_id=listing_id,
            )

            _transition_approval(
                approval_id=approval_id,
                from_status="PENDING_PUBLISH",
                to_status="PUBLISHED",
                values={
                    "listing_id": listing_id,
                    "published_at": _now(),
                },
            )

            return _response(
                200,
                f"""
                <h2>Published successfully.</h2>
                <p>SKU: {html.escape(sku)}</p>
                <p>Listing ID:
                <strong>{html.escape(listing_id)}</strong>
                </p>
                <p>
                <a href="https://www.ebay.co.uk/itm/{html.escape(listing_id)}">
                Open live eBay listing
                </a>
                </p>
                """,
            )

        return _response(
            400,
            "<h2>Unknown approval action.</h2>",
        )

    except ValueError as exc:
        return _response(
            400,
            (
                "<h2>Request could not be completed.</h2>"
                f"<p>{html.escape(str(exc))}</p>"
            ),
        )

    except Exception:
        return _response(
            500,
            (
                "<h2>Something went wrong.</h2>"
                "<p>No listing action was completed.</p>"
            ),
        )
