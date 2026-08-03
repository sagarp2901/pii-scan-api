"""
Minimal example client — no SDK required, just `requests`.

Usage:
    pip install requests
    export PII_SCAN_API_URL="https://your-api-id.execute-api.us-east-1.amazonaws.com/v1"
    export PII_SCAN_API_KEY="your-key"
    python3 examples/python_client.py
"""
import os
import time
import requests

API_URL = os.environ["PII_SCAN_API_URL"].rstrip("/")
API_KEY = os.environ["PII_SCAN_API_KEY"]
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def scan(text: str, redact: bool = True) -> dict:
    resp = requests.post(f"{API_URL}/scan", headers=HEADERS, json={"text": text, "redact": redact})
    resp.raise_for_status()
    return resp.json()


def scan_batch(rows: list[str]) -> str:
    resp = requests.post(f"{API_URL}/scan/batch", headers=HEADERS, json={"rows": rows})
    resp.raise_for_status()
    return resp.json()["job_id"]


def wait_for_batch(job_id: str, poll_seconds: float = 2.0) -> dict:
    while True:
        resp = requests.get(f"{API_URL}/scan/batch/{job_id}", headers=HEADERS)
        resp.raise_for_status()
        job = resp.json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(poll_seconds)


if __name__ == "__main__":
    result = scan("My SSN is 123-45-6789, contact me at a@b.com")
    print("Single scan findings:", result["findings"])
    print("Redacted:", result["redacted_text"])

    job_id = scan_batch(["SSN 123-45-6789", "nothing sensitive here", "card 4111111111111111"])
    print(f"Batch job submitted: {job_id}")
    job = wait_for_batch(job_id)
    print("Batch status:", job["status"])
    if job.get("result_url"):
        results = requests.get(job["result_url"]).json()
        print("Batch results:", results)
