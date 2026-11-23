"""Deterministic and conservative comparison primitives for cross-document validation."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.verification import (
    ComparisonType,
    FindingResult,
    FindingSeverity,
)
from app.verification.normalization import (
    extract_postal_code,
    mask_account_number,
    normalize_account_number,
    normalize_address,
    normalize_entity_name,
    normalize_identifier,
    parse_and_normalize_date,
)
from app.verification.similarity import (
    compute_address_similarity,
    compute_company_name_similarity,
)

# Thresholds aligned with Section 5 of cross-document verification spec
HIGH_CONFIDENCE_THRESHOLD = 0.70
FUZZY_NAME_MATCH_THRESHOLD = 0.90
FUZZY_NAME_REVIEW_THRESHOLD = 0.75
FUZZY_ADDRESS_MATCH_THRESHOLD = 0.75
FUZZY_ADDRESS_REVIEW_THRESHOLD = 0.50


@dataclass
class ComparisonOutcome:
    """Outcome of a single field comparison execution."""
    result: FindingResult
    severity: FindingSeverity
    explanation: str
    similarity_score: Optional[float] = None
    comparison_summary: Optional[str] = None


def compare_exact_identifier(
    val1: Optional[str],
    val2: Optional[str],
    field_label: str = "Identifier",
    source1_label: str = "Source 1",
    source2_label: str = "Source 2",
    quality1: float = 1.0,
    quality2: float = 1.0,
    is_critical: bool = False,
) -> ComparisonOutcome:
    """Compares structured statutory identifiers (GSTIN, PAN, CIN, IFSC, etc.) exactly."""
    norm1 = normalize_identifier(val1)
    norm2 = normalize_identifier(val2)

    if not norm1 or not norm2:
        return ComparisonOutcome(
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation=f"Cannot compare {field_label}: Value is missing or empty in one or both sources.",
            comparison_summary=f"{source1_label}: '{norm1 or '—'}' vs {source2_label}: '{norm2 or '—'}'",
            similarity_score=0.0,
        )

    if norm1 == norm2:
        return ComparisonOutcome(
            result=FindingResult.MATCH,
            severity=FindingSeverity.INFO,
            explanation=f"{field_label} matches consistently between {source1_label} and {source2_label}.",
            comparison_summary=f"'{norm1}' == '{norm2}'",
            similarity_score=1.0,
        )

    # Identifiers do not match
    is_both_high_confidence = (quality1 >= HIGH_CONFIDENCE_THRESHOLD and quality2 >= HIGH_CONFIDENCE_THRESHOLD)

    if is_both_high_confidence:
        return ComparisonOutcome(
            result=FindingResult.CONFIRMED_DISCREPANCY,
            severity=FindingSeverity.CRITICAL if is_critical else FindingSeverity.WARNING,
            explanation=(
                f"Confirmed {field_label} mismatch: {source1_label} specifies '{norm1}' "
                f"whereas {source2_label} contains '{norm2}'."
            ),
            comparison_summary=f"{source1_label}: '{norm1}' ≠ {source2_label}: '{norm2}'",
            similarity_score=0.0,
        )
    else:
        low_source = source1_label if quality1 < HIGH_CONFIDENCE_THRESHOLD else source2_label
        return ComparisonOutcome(
            result=FindingResult.POTENTIAL_DISCREPANCY,
            severity=FindingSeverity.WARNING,
            explanation=(
                f"Potential {field_label} discrepancy requiring review: {source1_label} has '{norm1}' "
                f"while {source2_label} has '{norm2}'. Evidence in {low_source} has limited extraction confidence "
                f"({min(quality1, quality2):.2f})."
            ),
            comparison_summary=f"{source1_label}: '{norm1}' ~ {source2_label}: '{norm2}' (low confidence)",
            similarity_score=0.0,
        )


def compare_account_numbers(
    val1: Optional[str],
    val2: Optional[str],
    source1_label: str = "Vendor Profile",
    source2_label: str = "Bank Proof",
    quality1: float = 1.0,
    quality2: float = 1.0,
    is_critical: bool = True,
) -> ComparisonOutcome:
    """Compares bank account numbers with strict zero-leakage masking in all findings and summaries."""
    norm1 = normalize_account_number(val1)
    norm2 = normalize_account_number(val2)

    masked1 = mask_account_number(val1)
    masked2 = mask_account_number(val2)

    if not norm1 or not norm2:
        return ComparisonOutcome(
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation=f"Cannot compare Bank Account Number: Unpopulated or unreadable in one or both sources.",
            comparison_summary=f"{source1_label}: {masked1} vs {source2_label}: {masked2}",
            similarity_score=0.0,
        )

    if norm1 == norm2:
        return ComparisonOutcome(
            result=FindingResult.MATCH,
            severity=FindingSeverity.INFO,
            explanation=f"Bank Account Number matches between {source1_label} and {source2_label}.",
            comparison_summary=f"{masked1} == {masked2}",
            similarity_score=1.0,
        )

    is_both_high_confidence = (quality1 >= HIGH_CONFIDENCE_THRESHOLD and quality2 >= HIGH_CONFIDENCE_THRESHOLD)

    if is_both_high_confidence:
        return ComparisonOutcome(
            result=FindingResult.CONFIRMED_DISCREPANCY,
            severity=FindingSeverity.CRITICAL if is_critical else FindingSeverity.WARNING,
            explanation=(
                f"Confirmed Bank Account Number mismatch: {source1_label} specifies {masked1} "
                f"whereas {source2_label} contains {masked2}."
            ),
            comparison_summary=f"{source1_label}: {masked1} ≠ {source2_label}: {masked2}",
            similarity_score=0.0,
        )
    else:
        low_source = source1_label if quality1 < HIGH_CONFIDENCE_THRESHOLD else source2_label
        return ComparisonOutcome(
            result=FindingResult.POTENTIAL_DISCREPANCY,
            severity=FindingSeverity.WARNING,
            explanation=(
                f"Potential Bank Account Number discrepancy: {source1_label} has {masked1} "
                f"while {source2_label} has {masked2}. Evidence in {low_source} has limited confidence ({min(quality1, quality2):.2f})."
            ),
            comparison_summary=f"{source1_label}: {masked1} ~ {source2_label}: {masked2} (low confidence)",
            similarity_score=0.0,
        )


def compare_dates(
    date_str1: Optional[str],
    date_str2: Optional[str],
    field_label: str = "Date",
    source1_label: str = "Source 1",
    source2_label: str = "Source 2",
    quality1: float = 1.0,
    quality2: float = 1.0,
    is_critical: bool = False,
) -> ComparisonOutcome:
    """Compares statutory dates after converting to canonical ISO 8601 representation."""
    iso1, valid1, amb1 = parse_and_normalize_date(date_str1)
    iso2, valid2, amb2 = parse_and_normalize_date(date_str2)

    if not valid1 or not valid2:
        return ComparisonOutcome(
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation=f"Cannot compare {field_label}: Unparseable or invalid date in one or both sources.",
            comparison_summary=f"{source1_label}: '{date_str1 or '—'}' vs {source2_label}: '{date_str2 or '—'}'",
            similarity_score=0.0,
        )

    if iso1 == iso2:
        return ComparisonOutcome(
            result=FindingResult.MATCH,
            severity=FindingSeverity.INFO,
            explanation=f"{field_label} matches consistently ({iso1}) between {source1_label} and {source2_label}.",
            comparison_summary=f"'{iso1}' == '{iso2}'",
            similarity_score=1.0,
        )

    # Dates differ: check if either was numerically ambiguous (e.g. 03/04/2024 vs 04/03/2024)
    if amb1 or amb2:
        return ComparisonOutcome(
            result=FindingResult.POTENTIAL_DISCREPANCY,
            severity=FindingSeverity.WARNING,
            explanation=(
                f"Potential {field_label} variation due to ambiguous date format: "
                f"{source1_label} parsed as '{iso1}' while {source2_label} parsed as '{iso2}'. "
                "Human review is recommended to verify day/month convention."
            ),
            comparison_summary=f"{source1_label}: '{iso1}' ~ {source2_label}: '{iso2}' (ambiguous format)",
            similarity_score=0.5,
        )

    is_both_high_confidence = (quality1 >= HIGH_CONFIDENCE_THRESHOLD and quality2 >= HIGH_CONFIDENCE_THRESHOLD)

    if is_both_high_confidence:
        return ComparisonOutcome(
            result=FindingResult.CONFIRMED_DISCREPANCY,
            severity=FindingSeverity.CRITICAL if is_critical else FindingSeverity.WARNING,
            explanation=(
                f"Confirmed {field_label} mismatch: {source1_label} specifies '{iso1}' "
                f"whereas {source2_label} states '{iso2}'."
            ),
            comparison_summary=f"{source1_label}: '{iso1}' ≠ {source2_label}: '{iso2}'",
            similarity_score=0.0,
        )
    else:
        low_source = source1_label if quality1 < HIGH_CONFIDENCE_THRESHOLD else source2_label
        return ComparisonOutcome(
            result=FindingResult.POTENTIAL_DISCREPANCY,
            severity=FindingSeverity.WARNING,
            explanation=(
                f"Potential {field_label} discrepancy: {source1_label} has '{iso1}' "
                f"while {source2_label} has '{iso2}'. Evidence in {low_source} has low extraction quality ({min(quality1, quality2):.2f})."
            ),
            comparison_summary=f"{source1_label}: '{iso1}' ~ {source2_label}: '{iso2}' (low confidence)",
            similarity_score=0.0,
        )


def compare_company_names(
    name1: Optional[str],
    name2: Optional[str],
    field_label: str = "Company Name",
    source1_label: str = "Source 1",
    source2_label: str = "Source 2",
    quality1: float = 1.0,
    quality2: float = 1.0,
    is_critical: bool = False,
) -> ComparisonOutcome:
    """Fuzzy and deterministic company name comparison with transparent similarity scoring."""
    norm1 = normalize_entity_name(name1)
    norm2 = normalize_entity_name(name2)

    if not norm1 or not norm2:
        return ComparisonOutcome(
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation=f"Cannot compare {field_label}: Company name is missing or empty in one or both sources.",
            comparison_summary=f"{source1_label}: '{name1 or '—'}' vs {source2_label}: '{name2 or '—'}'",
            similarity_score=0.0,
        )

    similarity = compute_company_name_similarity(norm1, norm2)

    if norm1 == norm2 or similarity >= FUZZY_NAME_MATCH_THRESHOLD:
        return ComparisonOutcome(
            result=FindingResult.MATCH,
            severity=FindingSeverity.INFO,
            explanation=f"{field_label} matches consistently between {source1_label} and {source2_label} (similarity: {similarity:.2f}).",
            comparison_summary=f"'{name1}' ~ '{name2}' ({similarity:.2f})",
            similarity_score=similarity,
        )

    is_both_high_confidence = (quality1 >= HIGH_CONFIDENCE_THRESHOLD and quality2 >= HIGH_CONFIDENCE_THRESHOLD)

    if similarity >= FUZZY_NAME_REVIEW_THRESHOLD:
        return ComparisonOutcome(
            result=FindingResult.POTENTIAL_DISCREPANCY,
            severity=FindingSeverity.WARNING,
            explanation=(
                f"Potential {field_label} discrepancy requiring review (similarity: {similarity:.2f}): "
                f"{source1_label} has '{name1}' while {source2_label} has '{name2}'. "
                "Significant token overlap observed; human review needed to confirm DBA or entity variation."
            ),
            comparison_summary=f"{source1_label}: '{name1}' ~ {source2_label}: '{name2}' ({similarity:.2f})",
            similarity_score=similarity,
        )

    # Low similarity (< FUZZY_NAME_REVIEW_THRESHOLD)
    if is_both_high_confidence:
        return ComparisonOutcome(
            result=FindingResult.CONFIRMED_DISCREPANCY,
            severity=FindingSeverity.CRITICAL if is_critical else FindingSeverity.WARNING,
            explanation=(
                f"Confirmed {field_label} mismatch: {source1_label} has '{name1}' "
                f"whereas {source2_label} specifies '{name2}' (similarity: {similarity:.2f})."
            ),
            comparison_summary=f"{source1_label}: '{name1}' ≠ {source2_label}: '{name2}' ({similarity:.2f})",
            similarity_score=similarity,
        )
    else:
        low_source = source1_label if quality1 < HIGH_CONFIDENCE_THRESHOLD else source2_label
        return ComparisonOutcome(
            result=FindingResult.POTENTIAL_DISCREPANCY,
            severity=FindingSeverity.WARNING,
            explanation=(
                f"Potential {field_label} conflict (similarity: {similarity:.2f}): "
                f"{source1_label} has '{name1}' vs {source2_label}: '{name2}'. "
                f"Evidence in {low_source} has low extraction quality ({min(quality1, quality2):.2f})."
            ),
            comparison_summary=f"{source1_label}: '{name1}' ~ {source2_label}: '{name2}' (low confidence)",
            similarity_score=similarity,
        )


def compare_addresses(
    addr1: Optional[str],
    addr2: Optional[str],
    field_label: str = "Registered Address",
    source1_label: str = "Source 1",
    source2_label: str = "Source 2",
    postal_code1: Optional[str] = None,
    postal_code2: Optional[str] = None,
    city1: Optional[str] = None,
    city2: Optional[str] = None,
    quality1: float = 1.0,
    quality2: float = 1.0,
    is_critical: bool = False,
) -> ComparisonOutcome:
    """Conservative address comparison evaluating structural components and overall similarity."""
    norm1 = normalize_address(addr1)
    norm2 = normalize_address(addr2)

    if not norm1 or not norm2:
        return ComparisonOutcome(
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation=f"Cannot compare {field_label}: Address value is missing in one or both sources.",
            comparison_summary=f"{source1_label}: '{addr1 or '—'}' vs {source2_label}: '{addr2 or '—'}'",
            similarity_score=0.0,
        )

    # Extract postal codes if not passed explicitly
    p1 = postal_code1 or extract_postal_code(addr1)
    p2 = postal_code2 or extract_postal_code(addr2)

    similarity, conflict_reason = compute_address_similarity(
        norm_addr1=norm1,
        norm_addr2=norm2,
        postal_code1=p1,
        postal_code2=p2,
        city1=city1,
        city2=city2,
    )

    if conflict_reason:
        is_both_high_confidence = (quality1 >= HIGH_CONFIDENCE_THRESHOLD and quality2 >= HIGH_CONFIDENCE_THRESHOLD)
        res = FindingResult.CONFIRMED_DISCREPANCY if is_both_high_confidence else FindingResult.POTENTIAL_DISCREPANCY
        return ComparisonOutcome(
            result=res,
            severity=FindingSeverity.CRITICAL if (is_critical and res == FindingResult.CONFIRMED_DISCREPANCY) else FindingSeverity.WARNING,
            explanation=f"Address conflict between {source1_label} and {source2_label}: {conflict_reason}.",
            comparison_summary=f"{conflict_reason} (similarity: {similarity:.2f})",
            similarity_score=similarity,
        )

    if norm1 == norm2 or similarity >= FUZZY_ADDRESS_MATCH_THRESHOLD:
        return ComparisonOutcome(
            result=FindingResult.MATCH,
            severity=FindingSeverity.INFO,
            explanation=f"{field_label} matches consistently between {source1_label} and {source2_label} (similarity: {similarity:.2f}).",
            comparison_summary=f"Address matched (similarity: {similarity:.2f})",
            similarity_score=similarity,
        )

    if similarity >= FUZZY_ADDRESS_REVIEW_THRESHOLD:
        return ComparisonOutcome(
            result=FindingResult.POTENTIAL_DISCREPANCY,
            severity=FindingSeverity.WARNING,
            explanation=(
                f"Potential {field_label} formatting variation (similarity: {similarity:.2f}): "
                f"{source1_label} and {source2_label} share major address components but differ in details."
            ),
            comparison_summary=f"Partial address match (similarity: {similarity:.2f})",
            similarity_score=similarity,
        )

    # Discrepancy
    is_both_high_confidence = (quality1 >= HIGH_CONFIDENCE_THRESHOLD and quality2 >= HIGH_CONFIDENCE_THRESHOLD)
    if is_both_high_confidence:
        return ComparisonOutcome(
            result=FindingResult.CONFIRMED_DISCREPANCY,
            severity=FindingSeverity.CRITICAL if is_critical else FindingSeverity.WARNING,
            explanation=(
                f"Confirmed {field_label} discrepancy: Significant mismatch between "
                f"{source1_label} and {source2_label} (similarity: {similarity:.2f})."
            ),
            comparison_summary=f"Address mismatch (similarity: {similarity:.2f})",
            similarity_score=similarity,
        )
    else:
        low_source = source1_label if quality1 < HIGH_CONFIDENCE_THRESHOLD else source2_label
        return ComparisonOutcome(
            result=FindingResult.POTENTIAL_DISCREPANCY,
            severity=FindingSeverity.WARNING,
            explanation=(
                f"Potential {field_label} discrepancy (similarity: {similarity:.2f}): "
                f"Evidence in {low_source} has low extraction quality ({min(quality1, quality2):.2f})."
            ),
            comparison_summary=f"Address review required (similarity: {similarity:.2f})",
            similarity_score=similarity,
        )
