"""Serverless human approval endpoint for commerce candidates.

GET
- validates the one-time approval token
- displays product/economics for review
- performs NO state change

POST
- validates the same one-time token
- approve: REVIEW -> APPROVED_FOR_LISTING
- reject: REVIEW -> REJECTED

This Lambda NEVER publishes to eBay.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import os
from datetime import datetime, timezone
from urllib.parse import parse_qs

import boto3
from botocore.exceptions import ClientError

from src.commerce.dynamo_storage import DynamoCommerceStore
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

queue = CandidateQueue(db=store)


def _response(
    status_code: int,
    body: str,
) -> dict:
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


def _get_approval(
    approval_id: str,
) -> dict | None:
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

    if not expected_hash or not hmac.compare_digest(
        supplied_hash,
        expected_hash,
    ):
        raise ValueError(
            "Approval token is invalid."
        )

    status = str(
        approval.get("status", "")
    )

    if status != "PENDING":
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

    candidate_id = approval.get(
        "candidate_id"
    )

    if not candidate_id:
        raise ValueError(
            "Approval request has no candidate."
        )

    return approval


def _review_page(
    *,
    approval_id: str,
    token: str,
    candidate,
) -> str:
    title = html.escape(candidate.title)
    sku = html.escape(candidate.sku)
    supplier = html.escape(
        candidate.supplier_id
    )

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
<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>
<title>3 Trading Agents Approval</title>

<style>
body {{
    font-family: Arial, sans-serif;
    max-width: 720px;
    margin: 40px auto;
    padding: 0 20px;
    color: #111;
}}

.card {{
    border: 1px solid #ddd;
    border-radius: 14px;
    padding: 24px;
}}

.details {{
    line-height: 1.8;
}}

button {{
    padding: 12px 18px;
    margin: 8px 8px 0 0;
    font-size: 16px;
    cursor: pointer;
}}

.approve {{
    background: #111;
    color: #fff;
    border: 1px solid #111;
}}

.reject {{
    background: #fff;
    color: #111;
    border: 1px solid #777;
}}

.warning {{
    margin-top: 22px;
    padding: 12px;
    background: #f4f4f4;
}}
</style>
</head>

<body>
<div class="card">

<h2>Product approval</h2>

<h3>{title}</h3>

<div class="details">
SKU: {sku}<br>
Supplier: {supplier}<br>
Target price: £{candidate.target_price:.2f}<br>
Supplier cost: £{candidate.supplier_cost:.2f}<br>
Expected profit: {profit}<br>
Expected margin: {margin}
</div>

<div class="warning">
Approving this step allows the system to prepare
the eBay listing. It does <strong>not</strong>
publish the listing.
</div>

<form method="post">

<input
    type="hidden"
    name="approval_id"
    value="{html.escape(approval_id)}"
>

<input
    type="hidden"
    name="token"
    value="{html.escape(token)}"
>

<button
    class="approve"
    type="submit"
    name="action"
    value="approve"
>
Approve Listing Preparation
</button>

<button
    class="reject"
    type="submit"
    name="action"
    value="reject"
>
Reject
</button>

</form>

</div>
</body>
</html>"""


def _parse_form(event: dict) -> dict[str, str]:
    if event.get("isBase64Encoded"):
        raise ValueError(
            "Base64 request body is not supported."
        )

    body = event.get("body") or ""

    parsed = parse_qs(
        body,
        keep_blank_values=True,
    )

    return {
        key: values[0]
        for key, values in parsed.items()
        if values
    }


def _close_approval(
    *,
    approval_id: str,
    decision: str,
) -> None:
    now = datetime.now(
        timezone.utc
    ).isoformat()

    try:
        table.update_item(
            Key={
                "PK": f"APPROVAL#{approval_id}",
                "SK": "META",
            },
            UpdateExpression=(
                "SET #status = :decision, "
                "decided_at = :now"
            ),
            ConditionExpression=(
                "#status = :pending"
            ),
            ExpressionAttributeNames={
                "#status": "status",
            },
            ExpressionAttributeValues={
                ":decision": decision,
                ":now": now,
                ":pending": "PENDING",
            },
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


def lambda_handler(
    event,
    context,
):
    request_context = (
        event.get("requestContext") or {}
    )

    http = (
        request_context.get("http") or {}
    )

    method = str(
        http.get("method", "GET")
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
                params.get(
                    "approval_id",
                    "",
                )
            )

            token = str(
                params.get(
                    "token",
                    "",
                )
            )

            approval = _validate_approval(
                approval_id,
                token,
            )

            candidate = store.get_candidate(
                str(
                    approval[
                        "candidate_id"
                    ]
                )
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
                    (
                        "<h2>Candidate is no longer "
                        "awaiting review.</h2>"
                    ),
                )

            return _response(
                200,
                _review_page(
                    approval_id=approval_id,
                    token=token,
                    candidate=candidate,
                ),
            )

        if method == "POST":
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

            approval = _validate_approval(
                approval_id,
                token,
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
                return _response(
                    409,
                    (
                        "<h2>Candidate is no longer "
                        "awaiting review.</h2>"
                    ),
                )

            if action == "approve":
                updated = (
                    queue.approve_for_listing(
                        candidate_id=candidate_id,
                        reviewer=(
                            "secure-web-approval"
                        ),
                        notes=(
                            "Approved through "
                            "serverless approval page."
                        ),
                    )
                )

                _close_approval(
                    approval_id=approval_id,
                    decision="APPROVED",
                )

                return _response(
                    200,
                    (
                        "<h2>Approved.</h2>"
                        f"<p>{html.escape(updated.title)}</p>"
                        "<p>The product is approved "
                        "for listing preparation.</p>"
                        "<p><strong>It has not been "
                        "published to eBay.</strong></p>"
                    ),
                )

            if action == "reject":
                updated = queue.reject(
                    candidate_id=candidate_id,
                    reason=(
                        "Rejected through "
                        "serverless approval page."
                    ),
                )

                _close_approval(
                    approval_id=approval_id,
                    decision="REJECTED",
                )

                return _response(
                    200,
                    (
                        "<h2>Rejected.</h2>"
                        f"<p>{html.escape(updated.title)}</p>"
                    ),
                )

            return _response(
                400,
                "<h2>Unknown approval action.</h2>",
            )

        return _response(
            405,
            "<h2>Method not allowed.</h2>",
        )

    except ValueError as exc:
        return _response(
            400,
            (
                "<h2>Approval request could "
                "not be completed.</h2>"
                f"<p>{html.escape(str(exc))}</p>"
            ),
        )

    except Exception:
        # Deliberately avoid exposing AWS/eBay/internal
        # exception details to the browser.
        return _response(
            500,
            (
                "<h2>Something went wrong.</h2>"
                "<p>The request was not completed.</p>"
            ),
        )
