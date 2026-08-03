import json
import sys
import uuid
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.detector import scan_text, redact_text
from common.model_backend import TinyLlamaBackend, scan_with_model, merge_findings
from common.dynamo import increment_usage, get_usage
from common.auth import extract_api_key, plan_limit_for

# Loaded once per container (not per request) — this is what makes warm
# invocations fast despite the model load cost on cold start.
_backend = TinyLlamaBackend()


def _response(status: int, body: dict):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


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

    redact = bool(payload.get("redact", False))

    regex_findings = scan_text(text)
    model_findings = scan_with_model(text, _backend)
    findings = merge_findings(regex_findings, model_findings)

    # Model-based scans process more data per call (a full LLM forward pass
    # vs. a regex match), so they're metered at a higher unit cost.
    units = increment_usage(api_key, units=5)

    body = {
        "id": f"scan_{uuid.uuid4().hex[:12]}",
        "findings": [f.to_dict() for f in findings],
        "usage": {"billed_units": 5, "period_total": units},
    }
    if redact:
        body["redacted_text"] = redact_text(text, findings)

    return _response(200, body)
