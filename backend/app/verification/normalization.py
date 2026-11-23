"""Deterministic normalizers for cross-document value comparison."""

import re
from datetime import datetime
from typing import Dict, Optional, Tuple


def normalize_identifier(val: Optional[str]) -> str:
    """Normalizes structured statutory identifiers (GSTIN, PAN, CIN, IFSC, etc.).
    
    Removes surrounding and interior whitespace, hyphens, and standardizes to uppercase.
    Preserves all alphanumeric characters without altering semantic content.
    """
    if not val:
        return ""
    clean = str(val).strip().upper()
    # Remove hyphens, colons, and spaces
    clean = re.sub(r"[\s\-_:]+", "", clean)
    return clean


def normalize_account_number(val: Optional[str]) -> str:
    """Extracts raw account digits, stripping spaces and punctuation."""
    if not val:
        return ""
    clean = str(val).strip()
    digits = re.sub(r"[^\d]", "", clean)
    return digits


def mask_account_number(val: Optional[str]) -> str:
    """Masks banking account numbers for safe display in findings and audit logs."""
    if not val:
        return "••••"
    digits = normalize_account_number(val)
    if not digits:
        return "••••"
    if len(digits) <= 4:
        return f"••••{digits}"
    return f"••••••••{digits[-4:]}"


def normalize_entity_name(name: Optional[str]) -> str:
    """Normalizes company and legal entity names for deterministic and fuzzy comparison.
    
    Applies conservative canonical rules:
    - Lowercase
    - Removes punctuation (commas, periods, single/double quotes, ampersands -> 'and')
    - Standardizes common legal suffixes ('private limited' -> 'pvt ltd', 'limited' -> 'ltd', 'incorporated' -> 'inc')
    - Collapses multiple whitespace into a single space
    """
    if not name:
        return ""
    clean = str(name).strip().lower()
    
    # Replace ampersands with 'and'
    clean = re.sub(r"&", " and ", clean)
    
    # Remove punctuation
    clean = re.sub(r"[\.,'\"/\\#\(\)\[\]]", " ", clean)
    
    # Collapse spaces
    clean = re.sub(r"\s+", " ", clean).strip()
    
    # Suffix normalization patterns
    suffix_rules = [
        (r"\bprivate\s+limited\b", "pvt ltd"),
        (r"\bpvt\s+ltd\b", "pvt ltd"),
        (r"\bpvt\s+limited\b", "pvt ltd"),
        (r"\bprivate\s+ltd\b", "pvt ltd"),
        (r"\blimited\b", "ltd"),
        (r"\bincorporated\b", "inc"),
        (r"\bcorporation\b", "corp"),
        (r"\bcompany\b", "co"),
        (r"\bpublic\s+limited\s+company\b", "plc"),
        (r"\bl\.l\.c\b", "llc"),
        (r"\bl\.l\.p\b", "llp"),
    ]
    for pattern, replacement in suffix_rules:
        clean = re.sub(pattern, replacement, clean)
        
    # Re-collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


# Aliases for convenience
normalize_company_name = normalize_entity_name


def normalize_date_str(val: Optional[str]) -> Tuple[Optional[str], bool]:
    """Convenience wrapper returning (iso_date_or_none, is_ambiguous)."""
    iso_date, is_valid, is_ambiguous = parse_and_normalize_date(val)
    return (iso_date if is_valid else None, is_ambiguous)


def parse_and_normalize_date(date_str: Optional[str]) -> Tuple[Optional[str], bool, bool]:
    """Parses diverse statutory date formats into a canonical ISO 8601 string (YYYY-MM-DD).
    
    Returns:
        (iso_date, is_valid, is_ambiguous)
        
    Handles formats:
    - 2024-04-15
    - 15/04/2024, 15-04-2024
    - 15-Apr-2024, 15 April 2024
    - Apr 15, 2024
    - 2024/04/15
    
    Ambiguity rule:
    If numerical format has day <= 12 and month <= 12 (e.g. 03/04/2024), marks is_ambiguous=True
    so that downstream engines do not treat a format interpretation difference as a confirmed discrepancy.
    """
    if not date_str or not str(date_str).strip():
        return (None, False, False)
        
    raw = str(date_str).strip()
    # Normalize separators
    clean = re.sub(r"[,\.]", " ", raw)
    clean = re.sub(r"\s+", " ", clean).strip()
    
    # Format candidates
    formats = [
        ("%Y-%m-%d", False),
        ("%Y/%m/%d", False),
        ("%d/%m/%Y", True),
        ("%d-%m-%Y", True),
        ("%d %m %Y", True),
        ("%m/%d/%Y", True),
        ("%m-%d-%Y", True),
        ("%d-%b-%Y", False),
        ("%d-%B-%Y", False),
        ("%d %b %Y", False),
        ("%d %B %Y", False),
        ("%b %d %Y", False),
        ("%B %d %Y", False),
    ]
    
    parsed_date = None
    is_ambiguous = False
    
    # Check for two-digit day/month ambiguity in purely numeric dates
    num_match = re.search(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", raw)
    if num_match:
        p1, p2 = int(num_match.group(1)), int(num_match.group(2))
        if 1 <= p1 <= 12 and 1 <= p2 <= 12 and p1 != p2:
            is_ambiguous = True

    for fmt, can_be_ambiguous in formats:
        try:
            dt = datetime.strptime(clean, fmt)
            # Sanity check year
            if 1900 <= dt.year <= 2100:
                parsed_date = dt.strftime("%Y-%m-%d")
                return (parsed_date, True, is_ambiguous)
        except ValueError:
            continue
            
    # Also attempt standard ISO format parsing if raw contains extra time
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return (dt.strftime("%Y-%m-%d"), True, False)
    except Exception:
        pass
        
    return (None, False, False)


def normalize_address(addr: Optional[str]) -> str:
    """Normalizes address text by standardizing abbreviations, punctuation, and whitespace."""
    if not addr:
        return ""
    clean = str(addr).strip().lower()
    
    # Remove punctuation
    clean = re.sub(r"[\.,'\"/\\#\(\)\[\]]", " ", clean)
    clean = re.sub(r"[\-_]", " ", clean)
    
    # Standardize common street abbreviations
    abbreviations = [
        (r"\brd\b", "road"),
        (r"\bst\b", "street"),
        (r"\bave\b", "avenue"),
        (r"\bblvd\b", "boulevard"),
        (r"\bdr\b", "drive"),
        (r"\bln\b", "lane"),
        (r"\bfl\b", "floor"),
        (r"\bflr\b", "floor"),
        (r"\bste\b", "suite"),
        (r"\bapt\b", "apartment"),
        (r"\bbldg\b", "building"),
        (r"\bopp\b", "opposite"),
        (r"\bnr\b", "near"),
        (r"\bno\b", "number"),
        (r"\bsec\b", "sector"),
        (r"\bsect\b", "sector"),
        (r"\bhr\b", "haryana"),
        (r"\bmh\b", "maharashtra"),
        (r"\bdl\b", "delhi"),
        (r"\bka\b", "karnataka"),
        (r"\btn\b", "tamil nadu"),
        (r"\bup\b", "uttar pradesh"),
        (r"\bgj\b", "gujarat"),
        (r"\bwb\b", "west bengal"),
        (r"\bts\b", "telangana"),
        (r"\bap\b", "andhra pradesh"),
        (r"\brj\b", "rajasthan"),
        (r"\bp\.?o\.?\s*box\b", "pobox"),
    ]
    for pattern, replacement in abbreviations:
        clean = re.sub(pattern, replacement, clean)
        
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


# Alias for address normalization
normalize_address_str = normalize_address


def extract_postal_code(text: Optional[str]) -> Optional[str]:
    """Extracts a postal code / PIN from address text."""
    if not text:
        return None
    # 6-digit Indian PIN (e.g. 560001) or 5-digit US ZIP (e.g. 94107)
    match = re.search(r"\b([1-9][0-9]{5})\b", text)
    if match:
        return match.group(1)
    match_us = re.search(r"\b([0-9]{5})(?:-[0-9]{4})?\b", text)
    if match_us:
        return match_us.group(1)
    return None
