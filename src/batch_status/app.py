import json
import os
import sys
import boto3

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.dynamo import get_job

s3 = boto3.client("s3")
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET")


def _response(status: int, body: dict):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


def handler(event, context):
    job_id = (event.get("pathParameters") or {}).get("job_id")
    if not job_id:
        return _response(400, {"error": "missing_job_id"})

    job = get_job(job_id)
    if not job:
        return _response(404, {"error": "not_found"})

    body = {
        "job_id": job["job_id"],
        "status": job["status"],
        "rows_processed": int(job.get("rows_processed", 0)),
        "estimated_rows": int(job.get("estimated_rows", 0)),
    }

    if job["status"] == "completed" and job.get("result_key"):
        # Presigned URL so the caller can download without new IAM creds.
        body["result_url"] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": RESULTS_BUCKET, "Key": job["result_key"]},
            ExpiresIn=3600,
        )

    return _response(200, body)
