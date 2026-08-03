import json
import os
import sys
import boto3

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.detector import scan_text
from common.dynamo import update_job, increment_usage

s3 = boto3.client("s3")
UPLOAD_BUCKET = os.environ["UPLOAD_BUCKET"]
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", UPLOAD_BUCKET)


def _process_job(job_id: str, input_key: str, api_key: str, entities):
    update_job(job_id, status="processing")

    obj = s3.get_object(Bucket=UPLOAD_BUCKET, Key=input_key)
    rows = json.loads(obj["Body"].read())

    results = []
    for i, row in enumerate(rows):
        text = row if isinstance(row, str) else json.dumps(row)
        findings = scan_text(text, entities=entities)
        results.append({"row": i, "findings": [f.to_dict() for f in findings]})

    result_key = input_key.replace("uploads/", "results/").rsplit(".", 1)[0] + "-results.json"
    s3.put_object(
        Bucket=RESULTS_BUCKET,
        Key=result_key,
        Body=json.dumps(results).encode("utf-8"),
        ServerSideEncryption="AES256",
        ContentType="application/json",
    )

    increment_usage(api_key, units=len(rows))
    update_job(
        job_id,
        status="completed",
        result_key=result_key,
        rows_processed=len(rows),
    )


def handler(event, context):
    # SQS may deliver a batch of messages in one invocation.
    for record in event.get("Records", []):
        msg = json.loads(record["body"])
        try:
            _process_job(msg["job_id"], msg["input_key"], msg["api_key"], msg.get("entities"))
        except Exception as e:  # noqa: BLE001 - surface failure on the job record
            update_job(msg["job_id"], status="failed", error=str(e))
            raise  # let SQS retry / DLQ per the queue's redrive policy
