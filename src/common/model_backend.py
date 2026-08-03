"""
Model-based detection backend — the extension point mentioned in
detector.py's module docstring. Catches free-text sensitive data that
regex can't: names, addresses, PHI phrased in prose, etc.

Kept as a separate, swappable interface (`ModelBackend`) rather than
importing transformers/torch directly into detector.py, so:
  - the free regex-only Lambda functions (ScanFunction, BatchWorkerFunction)
    stay lightweight and untouched
  - you can swap TinyLlama for SmolLM2 or anything else by implementing
    the same interface, without touching call sites
  - tests can inject a fake backend with zero model download / GPU needed
"""
import json
import re
from abc import ABC, abstractmethod
from typing import List

from .detector import Finding, _mask  # reuse the same Finding shape


class ModelBackend(ABC):
    @abstractmethod
    def extract_entities(self, text: str) -> List[dict]:
        """Return a list of {"type": str, "text": str, "start": int, "end": int}."""
        raise NotImplementedError


_PROMPT_TEMPLATE = """You are a sensitive-data detector. Find any PERSON names, \
PHYSICAL ADDRESSES, or PHI (health/medical information) mentioned in the text below.

Respond with ONLY a JSON array, no other text. Each item must have:
"type" (one of "PERSON", "ADDRESS", "PHI"), "text" (the exact substring found).
If nothing is found, respond with [].

Text: {text}

JSON:"""


class TinyLlamaBackend(ModelBackend):
    """
    TinyLlama-1.1B-Chat, loaded once per process (module-level cache keeps
    warm Lambda invocations fast — cold start pays the load cost, warm
    invocations don't). Apache 2.0 licensed, free to run — the cost that
    matters is compute, not licensing.

    Requires `transformers` + `torch`, which is why this lives behind a
    container-image Lambda (see Dockerfile) instead of the zip-based
    functions used for the regex-only endpoints.
    """

    MODEL_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"

    def __init__(self):
        self._pipe = None  # lazy-loaded on first use

    def _load(self):
        if self._pipe is not None:
            return
        from transformers import pipeline  # imported lazily so this module
        # stays importable in environments without transformers installed
        # (e.g. the regex-only Lambdas, or CI running detector-only tests).
        import torch

        self._pipe = pipeline(
            "text-generation",
            model=self.MODEL_ID,
            torch_dtype=torch.float32,
            device_map="cpu",
        )

    def extract_entities(self, text: str) -> List[dict]:
        self._load()
        prompt = _PROMPT_TEMPLATE.format(text=text)
        out = self._pipe(prompt, max_new_tokens=256, do_sample=False, return_full_text=False)
        raw = out[0]["generated_text"].strip()

        # Models occasionally wrap JSON in prose or code fences despite the
        # prompt — extract the first [...] block defensively.
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        try:
            items = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

        results = []
        for item in items:
            if not isinstance(item, dict) or "text" not in item or "type" not in item:
                continue
            span_start = text.find(item["text"])
            if span_start == -1:
                continue  # model hallucinated text not actually in the input
            results.append(
                {
                    "type": item["type"],
                    "text": item["text"],
                    "start": span_start,
                    "end": span_start + len(item["text"]),
                }
            )
        return results


def scan_with_model(text: str, backend: ModelBackend) -> List[Finding]:
    """Run the model backend and convert its raw output into Finding objects,
    matching the same shape the regex detector produces."""
    findings = []
    for item in backend.extract_entities(text):
        findings.append(
            Finding(
                type=item["type"],
                text_span=[item["start"], item["end"]],
                confidence=0.7,  # model-based findings get a flat, conservative
                                  # confidence pending real accuracy numbers from
                                  # the edge-LLM comparison paper's benchmarks
                matched_preview=_mask(item["text"]),
            )
        )
    return findings


def merge_findings(regex_findings: List[Finding], model_findings: List[Finding]) -> List[Finding]:
    """Combine both sources, dropping model findings that overlap a span the
    (more precise, checksum-validated) regex detector already caught."""
    def overlaps(a: Finding, b: Finding) -> bool:
        return a.text_span[0] < b.text_span[1] and b.text_span[0] < a.text_span[1]

    combined = list(regex_findings)
    for mf in model_findings:
        if not any(overlaps(mf, rf) for rf in regex_findings):
            combined.append(mf)

    combined.sort(key=lambda f: f.text_span[0])
    return combined
