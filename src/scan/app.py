import json
import sys
import uuid
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.detector import scan_text, redact_text
from common.dynamo import increment_usage, get_usage
from common.auth import extract_api_key, plan_limit_for


def _response(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
        },
        "body": json.dumps(body),
    }


def handler(event, context):
    api_key = extract_api_key(event)
    limit = plan_limit_for(api_key)

    if get_usage(api_key) >= limit:
        return _response(429, {"error": "quota_exceeded", "limit": limit})

    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid_json"})

    text = payload.get("text")
    if not text or not isinstance(text, str):
        return _response(400, {"error": "missing_field", "field": "text"})

    entities = payload.get("entities")  # optional filter list
    redact = bool(payload.get("redact", False))

    findings = scan_text(text, entities=entities)
    units = increment_usage(api_key, units=1)

    body = {
        "id": f"scan_{uuid.uuid4().hex[:12]}",
        "findings": [f.to_dict() for f in findings],
        "usage": {"billed_units": 1, "period_total": units},
    }
    if redact:
        body["redacted_text"] = redact_text(text, findings)

    return _response(200, body)
