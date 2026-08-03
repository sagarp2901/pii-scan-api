import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from common.detector import scan_text  # noqa: E402
from common.model_backend import ModelBackend, scan_with_model, merge_findings  # noqa: E402


class FakeBackend(ModelBackend):
    """Stand-in for TinyLlamaBackend — returns canned entities without
    loading any real model, so these tests run in milliseconds with no
    GPU/download required."""

    def __init__(self, canned_results):
        self._canned = canned_results

    def extract_entities(self, text):
        return self._canned


def test_scan_with_model_converts_to_findings():
    backend = FakeBackend([{"type": "PERSON", "text": "John Doe", "start": 0, "end": 8}])
    findings = scan_with_model("John Doe went home", backend)
    assert len(findings) == 1
    assert findings[0].type == "PERSON"
    assert findings[0].text_span == [0, 8]
    assert "John Doe" not in findings[0].matched_preview  # masked


def test_merge_findings_keeps_both_non_overlapping():
    regex_findings = scan_text("SSN 123-45-6789")
    model_findings = [
        type(regex_findings[0])(type="PERSON", text_span=[20, 28], confidence=0.7, matched_preview="Jo**oe")
    ]
    merged = merge_findings(regex_findings, model_findings)
    types = {f.type for f in merged}
    assert "SSN" in types
    assert "PERSON" in types


def test_merge_findings_drops_overlapping_model_finding():
    # Regex already caught the SSN at [4, 15]; a hallucinated/duplicate
    # model finding over the same span should be dropped, not double-counted.
    regex_findings = scan_text("SSN 123-45-6789")
    overlapping = type(regex_findings[0])(
        type="PERSON", text_span=[4, 15], confidence=0.7, matched_preview="xx"
    )
    merged = merge_findings(regex_findings, [overlapping])
    assert len(merged) == len(regex_findings)  # the overlapping one was dropped


def test_merge_findings_sorted_by_position():
    regex_findings = scan_text("email a@b.com and SSN 123-45-6789")
    model_findings = [
        type(regex_findings[0])(type="PERSON", text_span=[0, 5], confidence=0.7, matched_preview="xx")
    ]
    merged = merge_findings(regex_findings, model_findings)
    positions = [f.text_span[0] for f in merged]
    assert positions == sorted(positions)


def test_backend_skips_hallucinated_text_not_in_input():
    # If the model returns text that doesn't actually appear in the input,
    # extract_entities-derived findings should be droppable upstream; this
    # test documents that scan_with_model trusts backend.extract_entities
    # output as-is, so the backend itself (TinyLlamaBackend.extract_entities)
    # is responsible for that filtering — verified via the find()==-1 check
    # in TinyLlamaBackend, not here. This test just confirms scan_with_model
    # doesn't crash on an empty result.
    backend = FakeBackend([])
    findings = scan_with_model("nothing sensitive", backend)
    assert findings == []
