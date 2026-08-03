"""
Minimal API key extraction + plan lookup.

In production, back PLAN_LIMITS with a real customers table (or Stripe
metadata) instead of the hardcoded dict below.
"""
import os

FREE_TIER_LIMIT = int(os.environ.get("FREE_TIER_LIMIT", "1000"))

# TODO: replace with a lookup against a Customers table keyed by api_key
PLAN_LIMITS = {
    "default": FREE_TIER_LIMIT,
}


def extract_api_key(event: dict) -> str:
    headers = event.get("headers") or {}
    # API Gateway lower-cases header names for HTTP APIs; check both cases.
    auth = headers.get("authorization") or headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    # Fallback for local testing without a header.
    return headers.get("x-api-key", "anonymous")


def plan_limit_for(api_key: str) -> int:
    return PLAN_LIMITS.get(api_key, PLAN_LIMITS["default"])
