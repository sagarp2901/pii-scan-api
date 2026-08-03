import json
import os
import sys
import boto3

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.dynamo import create_job
from common.auth import extract_api_key

s3 = boto3.client("s3")
sqs = boto3.client("sqs")

UPLOAD_BUCKET = os.environ["UPLOAD_BUCKET"]
QUEUE_URL = os.environ["BATCH_QUEUE_URL"]


def _response(status: int, body: dict):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


def handler(event, context):
    api_key = extract_api_key(event)

    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid_json"})

    rows = payload.get("rows")          # inline list of strings, OR
    input_key = payload.get("input_key")  # an already-uploaded S3 object key
    entities = payload.get("entities")

    if not rows and not input_key:
        return _response(400, {"error": "missing_field", "field": "rows or input_key"})

    if rows:
        # Persist inline rows to S3 so the worker has one consistent input path.
        input_key = f"uploads/{api_key}/{context.aws_request_id}.json"
        s3.put_object(
            Bucket=UPLOAD_BUCKET,
            Key=input_key,
            Body=json.dumps(rows).encode("utf-8"),
            ServerSideEncryption="AES256",
            ContentType="application/json",
        )
        estimated_rows = len(rows)
    else:
        head = s3.head_object(Bucket=UPLOAD_BUCKET, Key=input_key)
        estimated_rows = int(head.get("Metadata", {}).get("row-count", 0))

    job_id = create_job(api_key, input_key, estimated_rows=estimated_rows)

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(
            {
                "job_id": job_id,
                "input_key": input_key,
                "api_key": api_key,
                "entities": entities,
            }
        ),
    )

    return _response(202, {"job_id": job_id, "status": "queued", "estimated_rows": estimated_rows})
