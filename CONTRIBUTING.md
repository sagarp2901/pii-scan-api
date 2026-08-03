# Contributing

Thanks for considering a contribution. This project is intentionally small
and dependency-light — please keep that spirit in mind.

## Getting set up

```bash
git clone https://github.com/sagarp2901/pii-scan-api.git
cd pii-scan-api
pip install -r requirements.txt pytest moto --break-system-packages
python3 -m pytest tests/ -v
```

No AWS account needed to run the test suite — the handler tests use `moto`
to mock AWS services.

## Ways to contribute

- **New entity detectors**: add a pattern (and validator, if needed) to
  `DETECTORS` in `src/common/detector.py`, plus tests in
  `tests/test_detector.py`. Keep detectors pure-stdlib where possible —
  that's what keeps Lambda cold starts fast and cheap.
- **Model-based detection**: `src/common/detector.py` is the intended
  extension point for small/edge LLM-based detection of entity types regex
  can't reliably catch (free-text PHI, names, addresses). A
  `detect_with_model()` function whose output gets merged with
  `scan_text()`'s findings is the expected shape — open an issue first to
  discuss approach/model choice before a large PR.
- **Bug fixes**: please include a test that reproduces the bug before the
  fix, where practical.
- **Docs**: README/SECURITY improvements are always welcome.

## Pull request process

1. Fork the repo and create a branch from `main`.
2. Make your change with tests.
3. Run `python3 -m pytest tests/ -v` — all tests must pass.
4. Open a PR with a clear description of the change and why.

## Code style

- Plain, readable Python. No heavyweight frameworks in the Lambda handlers —
  this keeps deploy packages small and cold starts fast.
- Prefer stdlib over new dependencies unless there's a strong reason
  (document it in the PR).

## Reporting bugs vs. security issues

Regular bugs: open a GitHub issue.
Security issues: see [SECURITY.md](SECURITY.md) — do not open a public
issue for those.
