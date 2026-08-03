import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.dynamo import get_usage
from common.auth import extract_api_key, plan_limit_for


def _response(status: int, body: dict):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


def handler(event, context):
    api_key = extract_api_key(event)
    used = get_usage(api_key)
    limit = plan_limit_for(api_key)
    return _response(
        200,
        {
            "api_key": api_key if api_key == "anonymous" else api_key[:8] + "...",
            "units_used": used,
            "units_limit": limit,
            "remaining": max(limit - used, 0),
        },
    )
