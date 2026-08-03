"""
Core sensitive-data detection engine.

Pure-stdlib baseline (regex + checksum validation) so it runs cheaply in a
small Lambda with no heavy ML dependencies and no cold-start model load.

Designed to be swapped/extended: add a `detect_with_model()` function that
calls an ONNX/small-LLM runtime and merge its findings with the ones here
for entity types regex can't reliably catch (e.g. free-text PHI).
"""
import re
from dataclasses import dataclass, asdict
from typing import List, Optional

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_SSN_RE = re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_CCN_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")


def _luhn_valid(number: str) -> bool:
    digits = [int(d) for d in re.sub(r"\D", "", number)]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


@dataclass
class Finding:
    type: str
    text_span: List[int]
    confidence: float
    matched_preview: str  # masked preview, never the raw match

    def to_dict(self):
        return asdict(self)


def _mask(s: str) -> str:
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + "*" * (len(s) - 4) + s[-2:]


DETECTORS = {
    "SSN": (_SSN_RE, 0.95, None),
    "EMAIL": (_EMAIL_RE, 0.9, None),
    "PHONE": (_PHONE_RE, 0.75, None),
    "CCN": (_CCN_RE, 0.9, _luhn_valid),
    "IPV4": (_IPV4_RE, 0.6, None),
}


def scan_text(text: str, entities: Optional[List[str]] = None) -> List[Finding]:
    """Scan a single string and return findings. `entities` optionally
    filters which detectors run (default: all)."""
    active = entities or list(DETECTORS.keys())
    findings: List[Finding] = []

    for etype in active:
        if etype not in DETECTORS:
            continue
        pattern, base_conf, validator = DETECTORS[etype]
        for m in pattern.finditer(text):
            matched = m.group(0)
            if validator and not validator(matched):
                continue
            findings.append(
                Finding(
                    type=etype,
                    text_span=[m.start(), m.end()],
                    confidence=base_conf,
                    matched_preview=_mask(matched),
                )
            )
    findings.sort(key=lambda f: f.text_span[0])
    return findings


def redact_text(text: str, findings: List[Finding]) -> str:
    """Replace each finding's span with [REDACTED:TYPE]. Applies from the
    end of the string backwards so earlier offsets stay valid."""
    result = text
    for f in sorted(findings, key=lambda x: x.text_span[0], reverse=True):
        start, end = f.text_span
        result = result[:start] + f"[REDACTED:{f.type}]" + result[end:]
    return result
