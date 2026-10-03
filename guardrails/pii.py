from __future__ import annotations

import re
from dataclasses import dataclass

# PHI/PII redaction applied before anything is logged or sent to a model.
# Regex-based: high recall on structured identifiers, not a full de-identification
# system (names in free text are only caught after "my name is" style cues).

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)")),
    ("MRN", re.compile(r"\b(?:mrn|medical record(?: number)?|patient id|member id)\s*[:#]?\s*[a-z0-9-]{4,}\b", re.I)),
    ("DATE", re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")),
    ("ADDRESS", re.compile(
        r"\b\d{1,6}\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Dr|Drive|Ln|Lane|Ct|Way)\b\.?")),
    ("ZIP", re.compile(r"\b\d{5}(?:-\d{4})\b")),
    ("NAME", re.compile(r"(?i:\b(my name is|i am called|patient name:?)\s+)[A-Z][a-z]+(?: [A-Z][a-z]+)?")),
]


@dataclass(frozen=True)
class RedactionResult:
    text: str
    found: tuple[str, ...]


def redact(text: str) -> RedactionResult:
    found: list[str] = []
    for label, pattern in _PATTERNS:
        if pattern.search(text):
            found.append(label)
            repl = (lambda m: m.group(1) + " [NAME]") if label == "NAME" else f"[{label}]"
            text = pattern.sub(repl, text)
    return RedactionResult(text, tuple(found))
