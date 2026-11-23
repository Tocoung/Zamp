"""Unit tests for cross-document verification comparison primitives, normalization, and similarity scoring."""

import pytest
from app.schemas.verification import FindingResult, FindingSeverity, ComparisonType
from app.verification.normalization import (
    normalize_identifier,
    normalize_account_number,
    normalize_company_name,
    normalize_date_str,
    normalize_address_str,
    mask_account_number,
)
from app.verification.similarity import (
    levenshtein_distance,
    token_sort_ratio,
    token_jaccard_similarity,
    evaluate_address_similarity,
)
from app.verification.comparison import (
    compare_exact_identifier,
    compare_account_numbers,
    compare_dates,
    compare_company_names,
    compare_addresses,
)


class TestNormalization:
    """Tests normalization functions for identifiers, accounts, names, dates, and addresses."""

    def test_normalize_identifier(self):
        assert normalize_identifier("27 AAAA A0000 A1Z5") == "27AAAAA0000A1Z5"
        assert normalize_identifier("27-aaaa-a0000-a1z5") == "27AAAAA0000A1Z5"
        assert normalize_identifier(None) == ""
        assert normalize_identifier("") == ""

    def test_normalize_account_number(self):
        assert normalize_account_number("1234 5678 9012") == "123456789012"
        assert normalize_account_number("1234-5678-9012") == "123456789012"
        assert normalize_account_number(None) == ""

    def test_mask_account_number(self):
        assert mask_account_number("123456789012") == "••••••••9012"
        assert mask_account_number("9012") == "••••9012"
        assert mask_account_number("") == "••••"
        assert mask_account_number(None) == "••••"

    def test_normalize_company_name(self):
        norm1 = normalize_company_name("Acme Technologies Private Limited")
        norm2 = normalize_company_name("ACME TECHNOLOGIES PVT. LTD.")
        norm3 = normalize_company_name("Acme Technologies Pvt Ltd")
        assert norm1 == norm2 == norm3 == "acme technologies pvt ltd"

        norm_corp = normalize_company_name("Global Services Corporation, Incorporated")
        assert "corporation" not in norm_corp
        assert "incorporated" not in norm_corp
        assert "corp" in norm_corp
        assert "inc" in norm_corp

    def test_normalize_date_str(self):
        # ISO format
        val, is_amb = normalize_date_str("2024-05-15")
        assert val == "2024-05-15"
        assert not is_amb

        # DD/MM/YYYY
        val, is_amb = normalize_date_str("15/05/2024")
        assert val == "2024-05-15"
        assert not is_amb

        # Ambiguous date where day <= 12 and month <= 12 and day != month
        val, is_amb = normalize_date_str("03/05/2024")
        assert is_amb

        # Impossible date
        val, is_amb = normalize_date_str("31/04/2024")
        assert val is None

    def test_normalize_address_str(self):
        addr1 = normalize_address_str("Plot 42, Sector 18, Rd No. 4, Gurugram, HR - 122001")
        assert "road" in addr1  # expands rd to road
        assert "-" not in addr1  # punctuation stripped


class TestSimilarityMetrics:
    """Tests fuzzy distance and similarity scoring."""

    def test_levenshtein_distance(self):
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("kitten", "sitting") == 3
        assert levenshtein_distance("same", "same") == 0

    def test_token_sort_ratio(self):
        assert token_sort_ratio("Acme Corp", "Corp Acme") == 1.0
        assert token_sort_ratio("Acme Technologies", "Acme Tech") < 1.0
        assert 0.0 <= token_sort_ratio("Alpha", "Beta") <= 1.0

    def test_token_jaccard_similarity(self):
        sim = token_jaccard_similarity("Plot 42 Sector 18 Gurugram", "Plot 42 Sector 18 Gurugram Haryana")
        assert 0.7 <= sim <= 1.0


class TestComparisonPrimitives:
    """Tests comparison handlers returning structured outcomes."""

    def test_exact_identifier_match(self):
        res = compare_exact_identifier("27AAAAA0000A1Z5", "27-aaaa-a0000-a1z5", "GSTIN", is_critical=True)
        assert res.result == FindingResult.MATCH
        assert res.similarity_score == 1.0
        assert res.severity == FindingSeverity.INFO

    def test_exact_identifier_mismatch(self):
        res = compare_exact_identifier("27AAAAA0000A1Z5", "29BBBBB1111B2Z6", "GSTIN", is_critical=True)
        assert res.result == FindingResult.CONFIRMED_DISCREPANCY
        assert res.similarity_score == 0.0
        assert res.severity == FindingSeverity.CRITICAL

    def test_exact_identifier_missing(self):
        res = compare_exact_identifier(None, "29BBBBB1111B2Z6", "GSTIN")
        assert res.result == FindingResult.INSUFFICIENT_EVIDENCE
        assert res.severity == FindingSeverity.INFO

    def test_account_numbers_match_and_masking(self):
        res = compare_account_numbers("123456789012", "1234 5678 9012")
        assert res.result == FindingResult.MATCH
        assert "123456789012" not in res.comparison_summary
        assert "••••••••9012" in res.comparison_summary

    def test_account_numbers_mismatch(self):
        res = compare_account_numbers("123456789012", "987654321098")
        assert res.result == FindingResult.CONFIRMED_DISCREPANCY
        assert res.severity == FindingSeverity.CRITICAL

    def test_date_comparison_matching(self):
        res = compare_dates("15/05/2024", "2024-05-15", "Incorporation Date")
        assert res.result == FindingResult.MATCH

    def test_date_comparison_mismatch(self):
        res = compare_dates("15/05/2024", "2023-01-10", "Incorporation Date")
        assert res.result == FindingResult.CONFIRMED_DISCREPANCY

    def test_company_name_comparison_minor_variation(self):
        res = compare_company_names(
            "Acme Technologies Private Limited",
            "Acme Technologies Pvt. Ltd.",
            "Legal Entity Name",
            is_critical=True,
        )
        assert res.result == FindingResult.MATCH
        assert res.similarity_score >= 0.90
        assert res.severity == FindingSeverity.INFO

    def test_company_name_comparison_conflict(self):
        res = compare_company_names(
            "Acme Technologies Private Limited",
            "Zenith Logistics India Pvt Ltd",
            "Legal Entity Name",
            is_critical=True,
        )
        assert res.result == FindingResult.CONFIRMED_DISCREPANCY
        assert res.severity == FindingSeverity.CRITICAL

    def test_company_name_comparison_partial(self):
        # Slightly related names that do not meet 0.85 threshold
        res = compare_company_names(
            "Acme Software Solutions Pvt Ltd",
            "Acme Hardware Systems Pvt Ltd",
            "Legal Entity Name",
            is_critical=True,
        )
        assert res.result in (FindingResult.POTENTIAL_DISCREPANCY, FindingResult.CONFIRMED_DISCREPANCY)
