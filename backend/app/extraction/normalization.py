"""Deterministic normalization layer for extracted document values."""

import re
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Tuple


@dataclass
class NormalizationRecord:
    """Detailed audit of a raw value's normalization and structural validity."""
    raw_value: Optional[str]
    normalized_value: Optional[str]
    masked_value: Optional[str] = None
    is_valid_format: bool = True
    is_ambiguous: bool = False
    was_repaired: bool = False
    repaired_chars: List[str] = field(default_factory=list)
    penalty: float = 0.0
    notes: List[str] = field(default_factory=list)

    @property
    def summary_note(self) -> Optional[str]:
        if not self.notes:
            return None
        return "; ".join(self.notes)


def _clean_field_text(raw: Optional[str]) -> str:
    """Strips leading/trailing delimiters, extra whitespace, and control characters."""
    if not raw:
        return ""
    v = re.sub(r"^[\s:\-=|/]+|[\s:\-=|/]+$", "", raw)
    return re.sub(r"\s+", " ", v).strip()


def normalize_gstin(raw: Optional[str]) -> NormalizationRecord:
    """Normalizes Indian GSTIN (15 characters) with OCR character repair tracking."""
    cleaned = _clean_field_text(raw).upper().replace(" ", "")
    if not cleaned:
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=None,
            is_valid_format=False,
            penalty=1.0,
            notes=["Empty or null GSTIN value"],
        )

    # Statutory India GSTIN regex: 2 digits + 5 alpha + 4 digits + 1 alpha + 1 alpha/num + 'Z' + 1 alpha/num
    strict_gstin_re = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"

    if re.match(strict_gstin_re, cleaned):
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=cleaned,
            masked_value=cleaned,
            is_valid_format=True,
            notes=["Valid 15-character statutory GSTIN syntax"],
        )

    # Check for possible OCR character repairs if length is 15
    if len(cleaned) == 15:
        chars = list(cleaned)
        repairs = []
        # State code positions 0, 1 should be digits
        for idx in (0, 1):
            if chars[idx] == "O":
                chars[idx] = "0"
                repairs.append(f"O->0 at pos {idx}")
            elif chars[idx] in ("I", "L"):
                chars[idx] = "1"
                repairs.append(f"{chars[idx]}->1 at pos {idx}")

        # PAN numeric segment positions 7, 8, 9, 10 should be digits
        for idx in (7, 8, 9, 10):
            if chars[idx] == "O":
                chars[idx] = "0"
                repairs.append(f"O->0 at pos {idx}")
            elif chars[idx] in ("I", "L"):
                chars[idx] = "1"
                repairs.append(f"{chars[idx]}->1 at pos {idx}")

        # Position 13 should be 'Z'
        if chars[13] in ("2", "7") and re.match(strict_gstin_re, "".join(chars[:13] + ["Z"] + chars[14:])):
            repairs.append(f"{chars[13]}->Z at pos 13")
            chars[13] = "Z"

        repaired_str = "".join(chars)
        if re.match(strict_gstin_re, repaired_str):
            return NormalizationRecord(
                raw_value=raw,
                normalized_value=repaired_str,
                masked_value=repaired_str,
                is_valid_format=True,
                was_repaired=True,
                repaired_chars=repairs,
                penalty=0.20,
                notes=[f"Repaired OCR character confusion: {', '.join(repairs)}"],
            )

    # Malformed or unsupported syntax
    return NormalizationRecord(
        raw_value=raw,
        normalized_value=cleaned,
        masked_value=cleaned,
        is_valid_format=False,
        penalty=0.50,
        notes=["GSTIN does not conform to 15-character statutory syntax"],
    )


def _is_valid_calendar_date(year: int, month: int, day: int) -> Tuple[bool, Optional[date], Optional[str]]:
    """Validates that a combination of year, month, and day represents a real calendar date."""
    try:
        d = date(year, month, day)
        return True, d, None
    except ValueError as e:
        return False, None, str(e)


def normalize_date(raw: Optional[str]) -> NormalizationRecord:
    """Normalizes dates to ISO 8601 (YYYY-MM-DD) with calendar validation and flags ambiguous numeric formats."""
    cleaned = _clean_field_text(raw).rstrip(",.")
    if not cleaned:
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=None,
            is_valid_format=False,
            penalty=1.0,
            notes=["Empty or null date value"],
        )

    # Strip ordinal suffixes: 1st, 2nd, 3rd, 15th
    clean_no_ordinal = re.sub(r"(\d+)(?:st|nd|rd|th)\b", r"\1", cleaned, flags=re.IGNORECASE)
    clean_no_ordinal = re.sub(r"\s+", " ", clean_no_ordinal).strip()

    # 1. First, check unambiguous ISO 8601 (YYYY-MM-DD or YYYY/MM/DD)
    iso_match = re.match(r"^(\d{4})([/\-\.])(\d{1,2})\2(\d{1,2})$", clean_no_ordinal)
    if iso_match:
        year = int(iso_match.group(1))
        month = int(iso_match.group(3))
        day = int(iso_match.group(4))
        is_cal_valid, _, err_msg = _is_valid_calendar_date(year, month, day)
        if is_cal_valid:
            iso_str = f"{year:04d}-{month:02d}-{day:02d}"
            return NormalizationRecord(
                raw_value=raw,
                normalized_value=iso_str,
                masked_value=iso_str,
                is_valid_format=True,
                notes=["Normalized ISO 8601 date"],
            )
        else:
            return NormalizationRecord(
                raw_value=raw,
                normalized_value=clean_no_ordinal,
                masked_value=clean_no_ordinal,
                is_valid_format=False,
                penalty=0.60,
                notes=[f"Invalid calendar date '{clean_no_ordinal}': {err_msg}"],
            )

    # 2. Check for numeric formats: DD/MM/YYYY or MM/DD/YYYY
    numeric_slash_match = re.match(r"^(\d{1,2})([/\-\.])(\d{1,2})\2(\d{4})$", clean_no_ordinal)
    if numeric_slash_match:
        part1 = int(numeric_slash_match.group(1))
        part2 = int(numeric_slash_match.group(3))
        year = int(numeric_slash_match.group(4))

        if 1 <= part1 <= 12 and 1 <= part2 <= 12:
            if part1 != part2:
                # Ambiguous! Cannot determine day vs month without guessing (both 1..12)
                return NormalizationRecord(
                    raw_value=raw,
                    normalized_value=clean_no_ordinal,
                    masked_value=clean_no_ordinal,
                    is_valid_format=True,
                    is_ambiguous=True,
                    penalty=0.45,
                    notes=[f"Ambiguous date format '{clean_no_ordinal}' (day/month could be {part1:02d}/{part2:02d} or {part2:02d}/{part1:02d}); requires operator verification"],
                )
            else:
                # Day and month are identical (e.g. 05/05/2024)
                is_cal_valid, _, err_msg = _is_valid_calendar_date(year, part1, part2)
                if is_cal_valid:
                    iso_str = f"{year:04d}-{part1:02d}-{part2:02d}"
                    return NormalizationRecord(
                        raw_value=raw,
                        normalized_value=iso_str,
                        masked_value=iso_str,
                        is_valid_format=True,
                        notes=["Normalized to ISO 8601 (YYYY-MM-DD)"],
                    )
                else:
                    return NormalizationRecord(
                        raw_value=raw,
                        normalized_value=clean_no_ordinal,
                        masked_value=clean_no_ordinal,
                        is_valid_format=False,
                        penalty=0.60,
                        notes=[f"Invalid calendar date '{clean_no_ordinal}': {err_msg}"],
                    )
        elif part1 > 12 and 1 <= part2 <= 12:
            # Unambiguously DD/MM/YYYY (day=part1, month=part2)
            is_cal_valid, _, err_msg = _is_valid_calendar_date(year, part2, part1)
            if is_cal_valid:
                iso_str = f"{year:04d}-{part2:02d}-{part1:02d}"
                return NormalizationRecord(
                    raw_value=raw,
                    normalized_value=iso_str,
                    masked_value=iso_str,
                    is_valid_format=True,
                    notes=[f"Normalized DD/MM/YYYY '{clean_no_ordinal}' to ISO 8601 '{iso_str}'"],
                )
            else:
                return NormalizationRecord(
                    raw_value=raw,
                    normalized_value=clean_no_ordinal,
                    masked_value=clean_no_ordinal,
                    is_valid_format=False,
                    penalty=0.60,
                    notes=[f"Invalid calendar date '{clean_no_ordinal}': day {part1} is invalid for month {part2} in year {year}"],
                )
        elif 1 <= part1 <= 12 and part2 > 12:
            # Unambiguously MM/DD/YYYY (month=part1, day=part2)
            is_cal_valid, _, err_msg = _is_valid_calendar_date(year, part1, part2)
            if is_cal_valid:
                iso_str = f"{year:04d}-{part1:02d}-{part2:02d}"
                return NormalizationRecord(
                    raw_value=raw,
                    normalized_value=iso_str,
                    masked_value=iso_str,
                    is_valid_format=True,
                    notes=[f"Normalized MM/DD/YYYY '{clean_no_ordinal}' to ISO 8601 '{iso_str}'"],
                )
            else:
                return NormalizationRecord(
                    raw_value=raw,
                    normalized_value=clean_no_ordinal,
                    masked_value=clean_no_ordinal,
                    is_valid_format=False,
                    penalty=0.60,
                    notes=[f"Invalid calendar date '{clean_no_ordinal}': day {part2} is invalid for month {part1} in year {year}"],
                )
        else:
            return NormalizationRecord(
                raw_value=raw,
                normalized_value=clean_no_ordinal,
                masked_value=clean_no_ordinal,
                is_valid_format=False,
                penalty=0.60,
                notes=[f"Invalid calendar date '{clean_no_ordinal}': both day and month exceed valid range"],
            )

    # 3. Check unambiguous standard formats with word months (e.g. "15 April 2021", "April 15, 2021")
    clean_unpunctuated = clean_no_ordinal.replace(",", "")
    clean_unpunctuated = re.sub(r"\s+", " ", clean_unpunctuated).strip()

    formats = (
        ("%d %B %Y", "%Y-%m-%d"),
        ("%d %b %Y", "%Y-%m-%d"),
        ("%B %d %Y", "%Y-%m-%d"),
        ("%b %d %Y", "%Y-%m-%d"),
    )
    for in_fmt, out_fmt in formats:
        try:
            dt = datetime.strptime(clean_unpunctuated, in_fmt)
            is_cal_valid, _, err_msg = _is_valid_calendar_date(dt.year, dt.month, dt.day)
            if is_cal_valid:
                iso_val = dt.strftime(out_fmt)
                return NormalizationRecord(
                    raw_value=raw,
                    normalized_value=iso_val,
                    masked_value=iso_val,
                    is_valid_format=True,
                    notes=[f"Normalized date to ISO 8601 '{iso_val}'"],
                )
        except ValueError:
            continue

    # Unrecognized date syntax or invalid calendar date
    return NormalizationRecord(
        raw_value=raw,
        normalized_value=clean_no_ordinal,
        masked_value=clean_no_ordinal,
        is_valid_format=False,
        penalty=0.60,
        notes=[f"Unrecognized date syntax or invalid calendar date '{clean_no_ordinal}'"],
    )


def normalize_entity_name(raw: Optional[str]) -> NormalizationRecord:
    """Normalizes legal entity name preserving uppercase statutory tokens (e.g. Pvt Ltd, LLC)."""
    cleaned = _clean_field_text(raw)
    if not cleaned:
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=None,
            is_valid_format=False,
            penalty=1.0,
            notes=["Empty or null entity name"],
        )

    # Strip redundant trailing punctuation or labels
    cleaned = re.sub(r"^(?:M/s\.?|Messrs\.?)\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) < 3:
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=cleaned,
            masked_value=cleaned,
            is_valid_format=False,
            penalty=0.50,
            notes=["Entity name too short (< 3 characters)"],
        )

    # Check if name is reasonable (not just digits/symbols)
    has_letters = bool(re.search(r"[A-Za-z]", cleaned))
    if not has_letters:
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=cleaned,
            masked_value=cleaned,
            is_valid_format=False,
            penalty=0.60,
            notes=["Entity name lacks alphabetic characters"],
        )

    return NormalizationRecord(
        raw_value=raw,
        normalized_value=cleaned,
        masked_value=cleaned,
        is_valid_format=True,
        notes=["Normalized whitespace and punctuation"],
    )


def normalize_address(raw: Optional[str]) -> NormalizationRecord:
    """Normalizes address string, repairing line-break hyphens while preserving locality/PIN."""
    if not raw:
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=None,
            is_valid_format=False,
            penalty=1.0,
            notes=["Empty or null address"],
        )

    # Fix hyphenated line breaks, e.g. "Indus-\ntrial" -> "Industrial"
    repaired = re.sub(r"([A-Za-z]{3,})-\s*\n\s*([A-Za-z]{3,})", r"\1\2", raw)
    # Collapse newlines and tabs to single spaces
    repaired = re.sub(r"[\r\n\t]+", " ", repaired)
    cleaned = _clean_field_text(repaired)

    if len(cleaned) < 8:
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=cleaned,
            masked_value=cleaned,
            is_valid_format=False,
            penalty=0.50,
            notes=["Address too short to represent complete premises location"],
        )

    return NormalizationRecord(
        raw_value=raw,
        normalized_value=cleaned,
        masked_value=cleaned,
        is_valid_format=True,
        notes=["Normalized line breaks and whitespace"],
    )


def normalize_ifsc(raw: Optional[str]) -> NormalizationRecord:
    """Normalizes Indian IFSC code (11 alphanumeric characters) with OCR zero repair."""
    cleaned = _clean_field_text(raw).upper().replace(" ", "")
    if not cleaned:
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=None,
            is_valid_format=False,
            penalty=1.0,
            notes=["Empty or null IFSC code"],
        )

    # Exact statutory 11-char regex: 4 alpha + '0' + 6 alphanumeric
    strict_ifsc_re = r"^[A-Z]{4}0[A-Z0-9]{6}$"
    if re.match(strict_ifsc_re, cleaned):
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=cleaned,
            masked_value=cleaned,
            is_valid_format=True,
            notes=["Valid 11-character statutory IFSC code"],
        )

    # Repair OCR confusion: position 4 as letter 'O' instead of digit '0'
    if len(cleaned) == 11 and cleaned[4] == "O":
        repaired = cleaned[:4] + "0" + cleaned[5:]
        if re.match(strict_ifsc_re, repaired):
            return NormalizationRecord(
                raw_value=raw,
                normalized_value=repaired,
                masked_value=repaired,
                is_valid_format=True,
                was_repaired=True,
                repaired_chars=["O->0 at pos 4"],
                penalty=0.15,
                notes=["Repaired OCR letter 'O' to digit '0' at 5th character"],
            )

    return NormalizationRecord(
        raw_value=raw,
        normalized_value=cleaned,
        masked_value=cleaned,
        is_valid_format=False,
        penalty=0.50,
        notes=["IFSC does not match 11-character statutory pattern (AAAA0CCCCCC)"],
    )


def normalize_account_number(raw: Optional[str]) -> NormalizationRecord:
    """Normalizes bank account number, enforces default masking (****1234), and rejects dummy values."""
    if not raw:
        return NormalizationRecord(
            raw_value=raw,
            normalized_value=None,
            is_valid_format=False,
            penalty=1.0,
            notes=["Empty or null account number"],
        )

    cleaned = re.sub(r"[^0-9]", "", str(raw))
    if len(cleaned) < 6 or len(cleaned) > 22:
        masked = "*" * len(cleaned) if cleaned else None
        return NormalizationRecord(
            raw_value="[REDACTED]",
            normalized_value=cleaned if cleaned else None,
            masked_value=masked,
            is_valid_format=False,
            penalty=0.60,
            notes=["Account number outside standard length (6-22 digits)"],
        )

    # Reject dummy placeholder sequences (e.g. all zeros or 12345678)
    if cleaned == "0" * len(cleaned) or cleaned == "12345678" or cleaned == "123456789":
        masked = "*" * (len(cleaned) - 4) + cleaned[-4:]
        return NormalizationRecord(
            raw_value="[REDACTED]",
            normalized_value=cleaned,
            masked_value=masked,
            is_valid_format=False,
            penalty=0.80,
            notes=["Dummy placeholder account sequence detected"],
        )

    masked = "*" * (len(cleaned) - 4) + cleaned[-4:]
    return NormalizationRecord(
        raw_value="[REDACTED]",
        normalized_value=cleaned,
        masked_value=masked,
        is_valid_format=True,
        notes=["Normalized account digits; masked by default for privacy"],
    )
