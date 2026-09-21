import os
import uuid

import boto3


TABLE_NAME = os.environ["COMMERCE_TABLE_NAME"]


def lambda_handler(event, context):
    table = boto3.resource("dynamodb").Table(TABLE_NAME)

    test_id = uuid.uuid4().hex[:8]
    pk = f"SMOKE#{test_id}"
    sk = "META"

    table.put_item(
        Item={
            "PK": pk,
            "SK": sk,
            "entity_type": "SMOKE_TEST",
            "status": "OK",
        }
    )

    response = table.get_item(
        Key={
            "PK": pk,
            "SK": sk,
        }
    )

    item = response.get("Item")

    if not item or item.get("status") != "OK":
        raise RuntimeError("DynamoDB smoke test failed")

    return {
        "ok": True,
        "pk": pk,
        "table": TABLE_NAME,
    }
