"""Deterministic document-specific information extraction parsers with provenance."""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from app.schemas.extraction import ExtractedField, FieldSource, FieldStatus
from app.extraction.ocr_engine import OcrDocumentResult, OcrPageResult


def _mask_account_number(acc: str) -> str:
    """Masks account number keeping only the last 4 digits (e.g. ****7890)."""
    clean = re.sub(r"[^0-9]", "", acc)
    if len(clean) <= 4:
        return "*" * len(clean)
    return "*" * (len(clean) - 4) + clean[-4:]


def _normalize_gstin_ocr(gstin: str) -> str:
    """Normalizes common OCR character confusions (O <-> 0) in 15-digit GSTIN."""
    gstin = gstin.upper().strip()
    if len(gstin) == 15:
        chars = list(gstin)
        if chars[0] == 'O': chars[0] = '0'
        if chars[1] == 'O': chars[1] = '0'
        for i in (7, 8, 9, 10):
            if chars[i] == 'O': chars[i] = '0'
        return ''.join(chars)
    return gstin


def _clean_field_value(raw: str) -> str:
    """Trims delimiters and extra whitespace from extracted string values."""
    v = re.sub(r"^[\s:\-=|/]+|[\s:\-=|/]+$", "", raw)
    return re.sub(r"\s+", " ", v).strip()


def _parse_iso_date(raw_date_str: str) -> Optional[str]:
    """Attempts parsing human-readable dates into ISO 8601 (YYYY-MM-DD)."""
    cleaned = raw_date_str.strip().rstrip(",.")
    cleaned = re.sub(r"(\d+)(?:st|nd|rd|th)", r"", cleaned)
    
    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B, %Y",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


class DocumentParser:
    """Extracts structured fields from OCR page results for a specific category schema."""

    def parse(
        self,
        document_id: str,
        category: str,
        ocr_result: OcrDocumentResult,
    ) -> Dict[str, ExtractedField]:
        normalized_cat = (category or "OTHER").upper()

        if normalized_cat == "TAX_CERTIFICATE":
            return self._parse_tax_certificate(document_id, ocr_result)
        elif normalized_cat == "BANK_PROOF":
            return self._parse_bank_proof(document_id, ocr_result)
        elif normalized_cat == "CERTIFICATE_OF_INCORPORATION":
            return self._parse_incorporation_certificate(document_id, ocr_result)
        elif normalized_cat == "ADDRESS_PROOF":
            return self._parse_address_proof(document_id, ocr_result)
        else:
            return self._parse_generic(document_id, ocr_result)

    # -------------------------------------------------------------------------
    # 1. TAX CERTIFICATE (GST / Tax ID)
    # -------------------------------------------------------------------------
    def _parse_tax_certificate(self, document_id: str, ocr: OcrDocumentResult) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}

        # gstin
        gstin_val, page_num, method, loc, snip = self._find_regex(
            ocr,
            r"(?:^|[^A-Z0-9])([0-9O]{2}[A-Z]{5}[0-9O]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})(?:$|[^A-Z0-9])"
        )
        if not gstin_val:
            gstin_val, page_num, method, loc, snip = self._find_regex(
                ocr,
                r"(?:Tax ID|PAN|EIN)[:\s]+([A-Z0-9\-]+)"
            )

        if gstin_val:
            gstin_val = _normalize_gstin_ocr(gstin_val)
        fields["gstin"] = self._build_field(
            "gstin", gstin_val, document_id, page_num, method, loc, snip, 0.98 if gstin_val else None
        )

        # legal_entity_name
        name_val, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Legal Name", r"Name of Business", r"Name of Taxpayer", r"Legal Entity Name", r"Trade Name"]
        )
        fields["legal_entity_name"] = self._build_field(
            "legal_entity_name", name_val, document_id, page_num, method, loc, snip, 0.92 if name_val else None
        )

        # registration_date
        date_raw, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Date of Registration", r"Registration Date", r"Date of Liability", r"Period of Validity from"]
        )
        parsed_date = _parse_iso_date(date_raw) if date_raw else None
        fields["registration_date"] = self._build_field(
            "registration_date", parsed_date, document_id, page_num, method, loc, snip, 0.95 if parsed_date else None
        )

        # registered_address
        addr_val, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Principal Place of Business", r"Registered Address", r"Address of Business", r"Address"]
        )
        fields["registered_address"] = self._build_field(
            "registered_address", addr_val, document_id, page_num, method, loc, snip, 0.88 if addr_val else None
        )

        return fields

    # -------------------------------------------------------------------------
    # 2. BANK PROOF
    # -------------------------------------------------------------------------
    def _parse_bank_proof(self, document_id: str, ocr: OcrDocumentResult) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}

        # account_holder_name
        name_val, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Account Holder(?: Name)?", r"Customer Name", r"Account Name", r"Beneficiary Name", r"Name"]
        )
        fields["account_holder_name"] = self._build_field(
            "account_holder_name", name_val, document_id, page_num, method, loc, snip, 0.92 if name_val else None
        )

        # bank_name
        bank_val = None
        for page in ocr.pages:
            for line_idx, line in enumerate(page.lines):
                known_banks = ["HDFC Bank", "ICICI Bank", "State Bank of India", "SBI", "Axis Bank", "Kotak Mahindra Bank", "Citibank", "JPMorgan Chase", "Bank of America", "Wells Fargo"]
                for b in known_banks:
                    if re.search(r"\b" + re.escape(b) + r"\b", line, re.IGNORECASE):
                        bank_val = b
                        page_num = page.page_number
                        method = page.extraction_method
                        loc = f"Page {page_num}, Line {line_idx + 1}"
                        snip = line[:100]
                        break
                if bank_val:
                    break
            if bank_val:
                break

        if not bank_val:
            bank_val, page_num, method, loc, snip = self._find_labeled_value(
                ocr,
                [r"Bank Name", r"Bank / Branch", r"Financial Institution"]
            )

        fields["bank_name"] = self._build_field(
            "bank_name", bank_val, document_id, page_num, method, loc, snip, 0.95 if bank_val else None
        )

        # account_number
        acc_val, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Account Number", r"A/c No\.?", r"Account No\.?", r"Account #"]
        )
        if not acc_val:
            acc_val, page_num, method, loc, snip = self._find_regex(
                ocr,
                r"(?:^|[^0-9])(\d{9,18})(?:$|[^0-9])"
            )

        masked = _mask_account_number(acc_val) if acc_val else None
        fields["account_number"] = self._build_field(
            "account_number", acc_val, document_id, page_num, method, loc, snip, 0.95 if acc_val else None, masked_value=masked
        )

        # ifsc_code
        ifsc_val, page_num, method, loc, snip = self._find_regex(
            ocr,
            r"(?:^|[^A-Z0-9])([A-Z]{4}0[A-Z0-9]{6})(?:$|[^A-Z0-9])"
        )
        if not ifsc_val:
            ifsc_val, page_num, method, loc, snip = self._find_labeled_value(
                ocr,
                [r"IFSC Code", r"IFSC", r"Routing Number", r"RTN"]
            )
        fields["ifsc_code"] = self._build_field(
            "ifsc_code", ifsc_val, document_id, page_num, method, loc, snip, 0.96 if ifsc_val else None
        )

        return fields

    # -------------------------------------------------------------------------
    # 3. CERTIFICATE OF INCORPORATION
    # -------------------------------------------------------------------------
    def _parse_incorporation_certificate(self, document_id: str, ocr: OcrDocumentResult) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}

        # legal_entity_name
        name_val, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"certifies that", r"Company Name", r"Corporate Name", r"Legal Name", r"Name of Company"]
        )
        fields["legal_entity_name"] = self._build_field(
            "legal_entity_name", name_val, document_id, page_num, method, loc, snip, 0.92 if name_val else None
        )

        # registration_number (CIN / Reg Number)
        reg_val, page_num, method, loc, snip = self._find_regex(
            ocr,
            r"(?:^|[^A-Z0-9])([LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6})(?:$|[^A-Z0-9])"
        )
        if not reg_val:
            reg_val, page_num, method, loc, snip = self._find_labeled_value(
                ocr,
                [r"Corporate Identity Number", r"CIN", r"Registration Number", r"Registration No\.?", r"Company Number"]
            )
        fields["registration_number"] = self._build_field(
            "registration_number", reg_val, document_id, page_num, method, loc, snip, 0.96 if reg_val else None
        )

        # incorporation_date
        inc_date_raw, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Date of Incorporation", r"Incorporated on", r"Date of Registration", r"Incorporation Date"]
        )
        parsed_date = _parse_iso_date(inc_date_raw) if inc_date_raw else None
        fields["incorporation_date"] = self._build_field(
            "incorporation_date", parsed_date, document_id, page_num, method, loc, snip, 0.95 if parsed_date else None
        )

        # country_of_incorporation
        country_val, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Country of Incorporation", r"Jurisdiction", r"Country"]
        )
        if not country_val:
            for page in ocr.pages:
                if re.search(r"\bIndia\b", page.text, re.IGNORECASE):
                    country_val = "India"
                    page_num = page.page_number
                    method = page.extraction_method
                    loc = f"Page {page_num}, Header"
                    snip = "Jurisdiction: India"
                    break

        fields["country_of_incorporation"] = self._build_field(
            "country_of_incorporation", country_val, document_id, page_num, method, loc, snip, 0.90 if country_val else None
        )

        return fields

    # -------------------------------------------------------------------------
    # 4. ADDRESS PROOF
    # -------------------------------------------------------------------------
    def _parse_address_proof(self, document_id: str, ocr: OcrDocumentResult) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}

        # entity_or_person_name
        name_val, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Customer Name", r"Consumer Name", r"Subscriber Name", r"Billed To", r"Name"]
        )
        fields["entity_or_person_name"] = self._build_field(
            "entity_or_person_name", name_val, document_id, page_num, method, loc, snip, 0.90 if name_val else None
        )

        # address
        addr_val, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Service Address", r"Billing Address", r"Premises Address", r"Installation Address", r"Address"]
        )
        fields["address"] = self._build_field(
            "address", addr_val, document_id, page_num, method, loc, snip, 0.88 if addr_val else None
        )

        # issuing_authority
        auth_val, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Issuing Authority", r"Service Provider", r"Utility Provider", r"Issuer", r"Authority"]
        )
        if not auth_val:
            for page in ocr.pages:
                known_issuers = ["Electricity Distribution Company", "Municipal Corporation", "Department of Telecommunications", "Tata Power", "BSES", "Airtel", "Vodafone"]
                for ki in known_issuers:
                    if re.search(r"\b" + re.escape(ki) + r"\b", page.text, re.IGNORECASE):
                        auth_val = ki
                        page_num = page.page_number
                        method = page.extraction_method
                        loc = f"Page {page_num}, Header Issuer"
                        snip = ki
                        break
                if auth_val:
                    break

        fields["issuing_authority"] = self._build_field(
            "issuing_authority", auth_val, document_id, page_num, method, loc, snip, 0.92 if auth_val else None
        )

        # document_date
        date_raw, page_num, method, loc, snip = self._find_labeled_value(
            ocr,
            [r"Bill Date", r"Issue Date", r"Invoice Date", r"Statement Date", r"Date"]
        )
        parsed_date = _parse_iso_date(date_raw) if date_raw else None
        fields["document_date"] = self._build_field(
            "document_date", parsed_date, document_id, page_num, method, loc, snip, 0.94 if parsed_date else None
        )

        return fields

    # -------------------------------------------------------------------------
    # GENERIC / FALLBACK
    # -------------------------------------------------------------------------
    def _parse_generic(self, document_id: str, ocr: OcrDocumentResult) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}
        name_val, page_num, method, loc, snip = self._find_labeled_value(ocr, [r"Name", r"Legal Name", r"Entity"])
        fields["entity_name"] = self._build_field("entity_name", name_val, document_id, page_num, method, loc, snip, 0.85 if name_val else None)

        date_val, page_num, method, loc, snip = self._find_labeled_value(ocr, [r"Date", r"Issue Date"])
        fields["document_date"] = self._build_field("document_date", _parse_iso_date(date_val) if date_val else None, document_id, page_num, method, loc, snip, 0.85 if date_val else None)
        return fields

    # -------------------------------------------------------------------------
    # HELPER PARSING LOGIC
    # -------------------------------------------------------------------------
    def _find_regex(
        self,
        ocr: OcrDocumentResult,
        pattern: str,
    ) -> Tuple[Optional[str], int, str, Optional[str], Optional[str]]:
        regex = re.compile(pattern, re.IGNORECASE)
        for page in ocr.pages:
            for line_idx, line in enumerate(page.lines):
                match = regex.search(line)
                if match:
                    val = match.group(1) if match.groups() else match.group(0)
                    loc = f"Page {page.page_number}, Line {line_idx + 1}"
                    snip = line[:120]
                    return val.strip(), page.page_number, page.extraction_method, loc, snip
        return None, 1, "DIGITAL_TEXT", None, None

    def _find_labeled_value(
        self,
        ocr: OcrDocumentResult,
        labels: List[str],
    ) -> Tuple[Optional[str], int, str, Optional[str], Optional[str]]:
        for label in labels:
            pattern = re.compile(rf"(?:{label})\s*[:\-=|]\s*(.+)", re.IGNORECASE)
            for page in ocr.pages:
                for line_idx, line in enumerate(page.lines):
                    match = pattern.search(line)
                    if match:
                        candidate = _clean_field_value(match.group(1))
                        if candidate and len(candidate) > 1:
                            loc = f"Page {page.page_number}, Line {line_idx + 1}"
                            snip = line[:120]
                            return candidate, page.page_number, page.extraction_method, loc, snip
                for line_idx in range(len(page.lines) - 1):
                    curr_line = page.lines[line_idx].strip()
                    if re.fullmatch(rf"(?:{label})\s*[:\-=|]?", curr_line, re.IGNORECASE):
                        next_line = _clean_field_value(page.lines[line_idx + 1])
                        if next_line and len(next_line) > 1:
                            loc = f"Page {page.page_number}, Lines {line_idx + 1}-{line_idx + 2}"
                            snip = f"{curr_line}: {next_line}"[:120]
                            return next_line, page.page_number, page.extraction_method, loc, snip

        return None, 1, "DIGITAL_TEXT", None, None

    def _build_field(
        self,
        name: str,
        value: Optional[str],
        doc_id: str,
        page_num: int,
        method: str,
        location: Optional[str],
        snippet: Optional[str],
        confidence: Optional[float] = None,
        masked_value: Optional[str] = None,
    ) -> ExtractedField:
        if value and str(value).strip():
            return ExtractedField(
                field_name=name,
                value=str(value).strip(),
                masked_value=masked_value or str(value).strip(),
                status=FieldStatus.EXTRACTED,
                confidence=confidence or 0.90,
                source=FieldSource(
                    document_id=doc_id,
                    page_number=page_num,
                    extraction_method=method,
                    evidence_location=location or f"Page {page_num}",
                    evidence_snippet=snippet,
                ),
                limitation_or_reason=None,
            )
        else:
            return ExtractedField(
                field_name=name,
                value=None,
                masked_value=None,
                status=FieldStatus.MISSING,
                confidence=None,
                source=FieldSource(
                    document_id=doc_id,
                    page_number=1,
                    extraction_method="DIGITAL_TEXT",
                    evidence_location=None,
                    evidence_snippet=None,
                ),
                limitation_or_reason="Field not detected in document content.",
            )


document_parser = DocumentParser()
