"""
DynamoDB access helpers. Two tables (created by template.yaml):

  UsageTable
    pk: api_key            (S)
    sk: period#YYYY-MM     (S)
    units                  (N)  -- incremented atomically per request

  JobsTable
    pk: job_id             (S)
    status, input_key, result_key, rows_processed, created_at, api_key
"""
import os
import time
import uuid
import boto3
from botocore.exceptions import ClientError

_dynamo = boto3.resource("dynamodb")
USAGE_TABLE = os.environ.get("USAGE_TABLE", "pii-scan-usage")
JOBS_TABLE = os.environ.get("JOBS_TABLE", "pii-scan-jobs")


def _period() -> str:
    return time.strftime("%Y-%m")


def increment_usage(api_key: str, units: int = 1) -> int:
    table = _dynamo.Table(USAGE_TABLE)
    resp = table.update_item(
        Key={"api_key": api_key, "sk": f"period#{_period()}"},
        UpdateExpression="ADD units :u SET updated_at = :t",
        ExpressionAttributeValues={":u": units, ":t": int(time.time())},
        ReturnValues="UPDATED_NEW",
    )
    return int(resp["Attributes"]["units"])


def get_usage(api_key: str) -> int:
    table = _dynamo.Table(USAGE_TABLE)
    try:
        resp = table.get_item(Key={"api_key": api_key, "sk": f"period#{_period()}"})
        return int(resp.get("Item", {}).get("units", 0))
    except ClientError:
        return 0


def check_quota(api_key: str, plan_limit: int) -> bool:
    """Returns True if the caller is still within their monthly quota."""
    return get_usage(api_key) < plan_limit


def create_job(api_key: str, input_key: str, estimated_rows: int = 0) -> str:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    table = _dynamo.Table(JOBS_TABLE)
    table.put_item(
        Item={
            "job_id": job_id,
            "status": "queued",
            "api_key": api_key,
            "input_key": input_key,
            "result_key": None,
            "rows_processed": 0,
            "estimated_rows": estimated_rows,
            "created_at": int(time.time()),
        }
    )
    return job_id


def update_job(job_id: str, **fields) -> None:
    table = _dynamo.Table(JOBS_TABLE)
    expr_parts, values, names = [], {}, {}
    for k, v in fields.items():
        expr_parts.append(f"#{k} = :{k}")
        names[f"#{k}"] = k
        values[f":{k}"] = v
    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def get_job(job_id: str) -> dict:
    table = _dynamo.Table(JOBS_TABLE)
    resp = table.get_item(Key={"job_id": job_id})
    return resp.get("Item")
