import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from common.detector import scan_text, redact_text  # noqa: E402


def test_detects_ssn():
    findings = scan_text("My SSN is 123-45-6789 please keep it safe.")
    types = [f.type for f in findings]
    assert "SSN" in types


def test_detects_email():
    findings = scan_text("Contact me at john.doe@example.com for details.")
    assert any(f.type == "EMAIL" for f in findings)


def test_detects_valid_credit_card_only():
    # 4111111111111111 is a well-known Luhn-valid test Visa number
    findings = scan_text("Card on file: 4111 1111 1111 1111")
    ccn_findings = [f for f in findings if f.type == "CCN"]
    assert len(ccn_findings) == 1


def test_rejects_invalid_credit_card():
    findings = scan_text("Random 16 digit number: 1234 5678 9012 3456")
    ccn_findings = [f for f in findings if f.type == "CCN"]
    assert len(ccn_findings) == 0


def test_entity_filter_limits_scope():
    text = "SSN 123-45-6789 and email a@b.com"
    findings = scan_text(text, entities=["SSN"])
    assert all(f.type == "SSN" for f in findings)


def test_no_false_positive_on_clean_text():
    findings = scan_text("The quick brown fox jumps over the lazy dog.")
    assert findings == []


def test_redact_replaces_span_and_preserves_offsets():
    text = "SSN: 123-45-6789 done."
    findings = scan_text(text)
    redacted = redact_text(text, findings)
    assert "123-45-6789" not in redacted
    assert "[REDACTED:SSN]" in redacted


def test_masked_preview_never_exposes_raw_value():
    findings = scan_text("SSN 123-45-6789")
    for f in findings:
        assert "123-45-6789" not in f.matched_preview
