import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "scan"))

import boto3
import pytest

pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402


@mock_aws
def test_scan_handler_end_to_end():
    # Set up a fake DynamoDB table before importing the handler module,
    # since dynamo.py creates its boto3 resource at import time.
    os.environ["USAGE_TABLE"] = "test-usage"
    os.environ["JOBS_TABLE"] = "test-jobs"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    ddb = boto3.resource("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="test-usage",
        KeySchema=[
            {"AttributeName": "api_key", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "api_key", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    if "scan.app" in sys.modules:
        del sys.modules["scan.app"]
    import app as scan_app  # noqa: E402

    event = {
        "headers": {"authorization": "Bearer test-key-123"},
        "body": json.dumps({"text": "SSN 123-45-6789, email a@b.com", "redact": True}),
    }

    resp = scan_app.handler(event, type("Ctx", (), {"aws_request_id": "abc"})())
    body = json.loads(resp["body"])

    assert resp["statusCode"] == 200
    types = {f["type"] for f in body["findings"]}
    assert "SSN" in types
    assert "EMAIL" in types
    assert "[REDACTED:SSN]" in body["redacted_text"]
    assert body["usage"]["period_total"] == 1
