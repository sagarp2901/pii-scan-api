# Security Policy

This project exists to help teams detect and protect sensitive data. We take
its own security seriously.

## Data handling

- **Single-entry scans (`/v1/scan`)** are processed in Lambda memory only and
  are never written to disk or persisted anywhere. The request payload is
  discarded once the response is returned.
- **Batch scans (`/v1/scan/batch`)** write inputs and results to S3 with
  server-side encryption enabled, and objects auto-expire after 3 days via a
  bucket lifecycle rule (see `template.yaml`).
- All API traffic is TLS-only. The S3 bucket policy denies any request that
  isn't made over `SecureTransport`.
- Findings returned by the API include a masked preview
  (`matched_preview`, e.g. `12*******89`) — the raw matched value is never
  included in logs or responses.

## Supported versions

This is an actively developed open-source project. Only the `main` branch
is supported; there are no maintained release branches at this time.

## Reporting a vulnerability

If you find a security issue (e.g. a way to bypass auth, exfiltrate another
customer's data, or an injection vector), please **do not open a public
GitHub issue**. Instead, email sagar.patel166@gmail.com with:

- A description of the issue and its potential impact
- Steps to reproduce
- Any relevant logs or request/response examples (with sensitive data
  redacted)

We'll acknowledge reports within a few days and aim to patch critical issues
promptly. Credit will be given in the changelog unless you prefer to remain
anonymous.

## Self-hosting security notes

If you deploy this into your own AWS account:

- Review IAM policies in `template.yaml` before deploying to production —
  they're scoped per-function but worth auditing for your own compliance
  requirements.
- Consider switching the API Gateway auth model from the current
  application-level bearer token check to a proper API Gateway usage plan
  or Lambda authorizer before handling real customer data (see the "Next
  steps" section of the README).
- If your compliance requirements need a customer-managed KMS key (for
  CloudTrail audit trails on every decrypt) instead of S3-managed
  encryption, see the README's KMS notes.
