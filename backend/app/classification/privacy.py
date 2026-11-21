"""Privacy protection and sensitive-identifier sanitization for document classification."""

import re
from typing import Dict, Any, List, Set
from app.classification.rules import (
    CATEGORY_STRONG_HEADINGS,
    CATEGORY_CONTEXT_KEYWORDS,
    CATEGORY_FILENAME_SIGNALS,
)

# Known allowed whitelist values for explainability evidence
ALLOWED_HEADINGS: Set[str] = {h for headings in CATEGORY_STRONG_HEADINGS.values() for h in headings}
ALLOWED_KEYWORDS: Set[str] = {k for keywords in CATEGORY_CONTEXT_KEYWORDS.values() for k in keywords}
ALLOWED_FILENAME_SIGNALS: Set[str] = {f for signals in CATEGORY_FILENAME_SIGNALS.values() for f in signals}

# Patterns for sensitive identifiers that must never appear in evidence, activity descriptions, or logs
# Note: In filenames, tokens are separated by underscores/dots/dashes. In regex \w includes '_',
# so we capture prefix separator (^|[^a-zA-Z0-9]) and preserve it with \g<1>[REDACTED_...].
SENSITIVE_PATTERNS = [
    # India GSTIN (15 chars)
    (re.compile(r"(^|[^a-zA-Z0-9])(\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})(?=[^a-zA-Z0-9]|$)", re.IGNORECASE), r"\g<1>[REDACTED_TAX_ID]"),
    # India PAN (10 chars: 5 letters, 4 digits, 1 letter)
    (re.compile(r"(^|[^a-zA-Z0-9])([A-Z]{5}\d{4}[A-Z])(?=[^a-zA-Z0-9]|$)", re.IGNORECASE), r"\g<1>[REDACTED_PAN]"),
    # US EIN (e.g. 12-3456789)
    (re.compile(r"(^|[^a-zA-Z0-9])(\d{2}-\d{7})(?=[^a-zA-Z0-9]|$)"), r"\g<1>[REDACTED_EIN]"),
    # Email addresses
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    # Numerical sequences of 4 or more digits (bank accounts, routing numbers, card numbers, phone numbers)
    (re.compile(r"(^|[^a-zA-Z0-9])(\d{4,})(?=[^a-zA-Z0-9]|$)"), r"\g<1>[REDACTED_NUM]"),
]


def mask_sensitive_identifiers(text: str) -> str:
    """Replaces sensitive identifiers and numerical sequences with explicit redactions."""
    if not text:
        return ""
    masked = str(text)
    for pattern, replacement in SENSITIVE_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked


def sanitize_filename_for_activity(filename: str) -> str:
    """Sanitizes filename for safe presentation in vendor activity logs and error descriptions."""
    return mask_sensitive_identifiers(filename)


def sanitize_evidence_dict(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures classification evidence contains only safe, generic classification signals.
    
    Guarantees:
    - Raw extracted text is NEVER included.
    - No sensitive numbers (bank accounts, tax IDs) or personal info are included.
    - Matched headings, keywords, and filename signals only contain recognized dictionary signals.
    """
    if not isinstance(evidence, dict):
        return {}

    # Filter headings to strictly valid allowed items
    raw_headings = evidence.get("matched_headings", [])
    safe_headings = [h for h in raw_headings if h in ALLOWED_HEADINGS]

    # Filter keywords to strictly valid allowed items
    raw_keywords = evidence.get("matched_keywords", [])
    safe_keywords = [k for k in raw_keywords if k in ALLOWED_KEYWORDS]

    # Filter secondary filename signals to strictly valid allowed items
    raw_fn_signals = evidence.get("secondary_filename_signals", [])
    safe_fn_signals = [f for f in raw_fn_signals if f in ALLOWED_FILENAME_SIGNALS]

    # Category signals (category name -> float)
    signals_by_cat = {}
    for cat, score in evidence.get("signals_by_category", {}).items():
        if cat in CATEGORY_STRONG_HEADINGS or cat == "UNKNOWN":
            try:
                signals_by_cat[cat] = float(score)
            except (ValueError, TypeError):
                signals_by_cat[cat] = 0.0

    return {
        "matched_headings": safe_headings,
        "matched_keywords": safe_keywords,
        "secondary_filename_signals": safe_fn_signals,
        "signals_by_category": signals_by_cat,
        "text_length_chars": int(evidence.get("text_length_chars", 0)),
    }
