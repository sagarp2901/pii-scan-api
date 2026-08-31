# clarity-guard

[![tests](https://github.com/sagarp2901/clarity-guard/actions/workflows/test.yml/badge.svg)](https://github.com/sagarp2901/clarity-guard/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Purpose

Most teams find out they have a sensitive-data problem after it's already a
breach, an audit finding, or a compliance violation — because detecting PII/PCI
buried in logs, API payloads, data pipelines, and internal tools is normally
either a manual review process or a large, expensive DLP platform integration.

**clarity-guard exists to make sensitive-data detection a five-minute add,
not a quarter-long project.** The goal is for any engineering team to be
able to drop a scan call into an existing API, ETL job, or internal
workflow and get back structured findings they can act on immediately —
flag it, redact it, block it, alert on it — instead of building detection
logic from scratch or shipping raw data to a third-party cloud service to
find out what's in it.

Two design choices follow directly from that goal:
- **It's an API, not a library you have to wire into your stack.** Any
  language, any service, any workflow tool that can make an HTTP call can
  use it — no SDK lock-in, no dependency tree to manage. Single entries and
  batches are both first-class, because real remediation workflows need
  both: a single API payload checked inline before it's logged, and a
  whole dataset swept before a migration or a compliance review.
- **It's self-hostable and open source.** Sensitive-data detection is a
  strange thing to outsource to a black-box cloud service — you'd be
  sending your sensitive data *to* the thing that's supposed to protect
  it. Running it in your own AWS account means the data never leaves your
  infrastructure, and the detection logic is fully auditable rather than
  a vendor's opaque model.

If you're building remediation workflows on top of this — auto-redaction
pipelines, compliance dashboards, CI checks that block PII from getting
committed, whatever — that's exactly the intended use. See
[CONTRIBUTING.md](CONTRIBUTING.md) if you want to extend the detection
engine itself, or just call the API from your own tooling as-is.

## Overview

Serverless sensitive-data (PII/PCI) scanning API. Single-entry (`/v1/scan`)
and batch (`/v1/scan/batch`) endpoints, pay-per-invocation, encrypted in
transit and at rest, with per-API-key usage metering.

Baseline detector is pure-stdlib regex + Luhn checksum (SSN, email, phone,
credit card, IPv4) — zero cold-start model load, near-zero compute cost.
`src/common/detector.py` is the single place to swap in or add an ONNX /
small-LLM model for entity types regex can't reliably catch (e.g. free-text
PHI) — call it alongside `scan_text()` and merge the findings lists.

## Two ways to use this

**1. Self-host it (free, this repo).** Deploy the SAM template into your own
AWS account. You control the data, the cost, and the model. This is the
recommended path if you're handling real sensitive data — nothing leaves
your AWS account.

**2. Call a hosted instance.** If you (or someone) deploys this and exposes
it publicly, anyone can call it like any other REST API — see "Calling the
API" below. No AWS account needed on the caller's side, just an API key
issued by whoever runs the instance.

This is an open-core model: the scanning engine and infrastructure-as-code
are fully open (MIT license) — a hosted convenience layer with billing on
top is an optional add-on, not a requirement to use the project.

## Architecture

```
POST /v1/scan            -> ScanFunction (sync, in Lambda memory only)
POST /v1/scan/batch      -> BatchSubmitFunction -> S3 (encrypted) + SQS
                             SQS -> BatchWorkerFunction -> S3 results
GET  /v1/scan/batch/{id} -> BatchStatusFunction (reads DynamoDB + presigns S3 URL)
GET  /v1/usage           -> UsageFunction
```

- **DynamoDB** (`UsageTable`, `JobsTable`) — pay-per-request billing mode, encrypted at rest.
- **S3** (`DataBucket`) — SSE-S3 (AES256) encryption, TLS-only bucket policy, 3-day lifecycle expiry, versioned.
- **SQS** (`BatchQueue` + DLQ) — decouples submission from processing; failed jobs redrive to a dead-letter queue after 3 attempts.

Single-entry scans are **not persisted** — the text is processed in Lambda
memory and discarded. Batch inputs/outputs live in S3 for 3 days (configurable
via the `ExpirationInDays` rule in `template.yaml`), then auto-delete.

## Prerequisites (for self-hosting)

- AWS account + credentials configured (`aws configure`)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Python 3.12
- Docker (only needed for `sam local` testing, not for deploy)

## Deploy

```bash
git clone https://github.com/sagarp2901/clarity-guard.git
cd clarity-guard
sam build
sam deploy --guided
```

`--guided` walks you through stack name, region, and confirms IAM changes.
It saves your answers to `samconfig.toml` so subsequent deploys are just
`sam deploy`. After it finishes, note the `ApiUrl` output — that's your base
URL.

To tear everything down later: `sam delete`.

## Local testing (no AWS deploy needed)

Unit tests cover the detection engine directly and the full `/v1/scan`
handler against a mocked AWS backend (via `moto`), so you can validate logic
before spending a single dollar on AWS:

```bash
pip install -r requirements.txt pytest moto --break-system-packages
python3 -m pytest tests/ -v
```

To run the API locally against real Lambda emulation (requires Docker):

```bash
sam local start-api
# in another terminal:
curl -X POST http://127.0.0.1:3000/scan \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"text": "My SSN is 123-45-6789", "redact": true}'
```

## Calling the API

Whether it's your own deployment or someone else's hosted instance — same
interface either way. Set `$API_URL` to the `ApiUrl` output from `sam
deploy` (it already includes the `/v1` stage prefix).

**Single scan:**
```bash
curl -X POST $API_URL/scan \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"text": "Card 4111 1111 1111 1111, email a@b.com", "redact": true}'
```

**Submit a batch job (inline rows):**
```bash
curl -X POST $API_URL/scan/batch \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"rows": ["SSN 123-45-6789", "no sensitive data here", "email x@y.com"]}'
# -> {"job_id": "job_xxx", "status": "queued", "estimated_rows": 3}
```

**Check job status / get results:**
```bash
curl $API_URL/scan/batch/job_xxx -H "Authorization: Bearer test-key"
# once completed, response includes a presigned "result_url" (valid 1 hour)
```

**Check usage:**
```bash
curl $API_URL/usage -H "Authorization: Bearer test-key"
```

**Python client:** see [`examples/python_client.py`](examples/python_client.py)
for a small `requests`-based wrapper covering all four endpoints, including
batch polling.

## Cost notes

- Single-entry path: API Gateway (HTTP API, cheaper than REST API) + Lambda,
  both pay-per-invocation, scale to zero. No idle cost.
- Batch path: SQS + a second Lambda, same pay-per-use model. `MemorySize` on
  `BatchWorkerFunction` is set higher (512MB) since it processes many rows
  per invocation — tune based on your real row-processing time.
- DynamoDB in `PAY_PER_REQUEST` mode — no provisioned capacity to pay for
  when idle.
- S3 lifecycle rule auto-expires objects after 3 days to bound storage cost.
- Uses S3-managed (SSE-S3/AES256) encryption by default — no per-key monthly
  charge. If your compliance needs require a customer-managed KMS key (for
  a CloudTrail audit trail on every decrypt), swap `SSEAlgorithm: AES256`
  back to `aws:kms` + a `AWS::KMS::Key` resource; budget ~$1/month per key
  for that.

## Adding metered billing (Stripe)

`src/common/auth.py` has a `PLAN_LIMITS` dict as a placeholder — swap it for
a lookup against a real Customers table (or Stripe customer metadata) keyed
by `api_key`. The usage counters in `UsageTable` are already structured by
`api_key` + monthly period, so a nightly sync job can read them and call
Stripe's usage-record API to bill overages, or you can call it in real time
from `increment_usage()` if you want live metering.

## Security

- TLS enforced: HTTP API is HTTPS-only by default; S3 bucket policy denies
  any non-`SecureTransport` request.
- All S3 objects encrypted at rest (SSE-S3 by default).
- DynamoDB encryption at rest enabled on both tables.
- No raw sensitive input is logged — `matched_preview` in findings is always
  masked, never the raw matched value.
- See [SECURITY.md](SECURITY.md) for the full data-handling policy and how
  to report a vulnerability.

## Publishing / contributing

This repo is set up to be pushed straight to GitHub — MIT license, CI
(`.github/workflows/test.yml` runs the test suite on every push/PR), a
`.gitignore` tuned for Python + SAM build artifacts, and
[CONTRIBUTING.md](CONTRIBUTING.md) for anyone who wants to add detectors or
a model-based detection layer.

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/sagarp2901/clarity-guard.git
git push -u origin main
```

## Model-based scan (TinyLlama)

`POST /scan/model` runs the same regex detection as `/scan`, plus a
TinyLlama-1.1B pass that catches free-text sensitive data regex can't —
names, addresses, PHI phrased in prose. Findings from both are merged
(overlapping spans from the model are dropped in favor of the more precise,
checksum-validated regex match).

```bash
curl -X POST $API_URL/scan/model \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"text": "Patient John Doe, 42 Elm Street, was seen for a follow-up.", "redact": true}'
```

**This is a separate, heavier deployment path from `/scan`:**
- Ships as a **container-image Lambda** (`Dockerfile`), not a zip package —
  `torch` + `transformers` + model weights don't fit in a zip-based
  function. Model weights are baked into the image at build time so cold
  starts don't also pay a network download.
- Needs significantly more memory (`8192 MB` vs `256 MB` for `/scan`) and
  costs proportionally more per invocation — billed at 5 usage units per
  call vs. 1 for the regex-only endpoint, reflecting the heavier compute.
- **API Gateway's 30-second integration timeout is a hard ceiling that
  can't be raised.** A cold-start invocation (model load + first inference)
  may exceed it. If that happens in practice: enable Provisioned
  Concurrency to keep the function warm (flat hourly cost instead of
  pay-per-use for that slice), call the Lambda directly via the SDK for
  batch/background use cases, or front it with a Lambda Function URL in
  streaming mode instead of API Gateway.
- Confidence scores for model findings are currently a flat `0.7` pending
  real accuracy numbers — tune this once you have benchmark data on
  TinyLlama's actual precision/recall for this task.

The regex-only `/scan` and `/scan/batch` endpoints are unaffected by any of
this — they stay on the original lightweight zip-based Lambdas with their
existing cost profile.

## Roadmap / next steps

- [ ] Swap `PLAN_LIMITS` placeholder for real Stripe-backed billing
- [x] Add a model-based detection hook (TinyLlama, see above) for free-text
      PHI detection, merged with regex findings
- [ ] Benchmark TinyLlama vs. SmolLM2 accuracy on this task and replace the
      flat 0.7 confidence score with real numbers
- [ ] API Gateway usage plan or Lambda authorizer for real key validation
      (current auth is application-level bearer-token metering, not
      cryptographic key verification)
- [ ] Optional customer-managed KMS mode for compliance-sensitive deployments
