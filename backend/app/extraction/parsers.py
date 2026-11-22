"""Deterministic document-specific information extraction parsers with explainable confidence and provenance."""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from app.schemas.extraction import ExtractedField, FieldSource, FieldStatus
from app.extraction.ocr_engine import OcrDocumentResult, OcrPageResult, OcrToken
from app.extraction.normalization import (
    NormalizationRecord,
    normalize_gstin,
    normalize_date,
    normalize_entity_name,
    normalize_address,
    normalize_ifsc,
    normalize_account_number,
)
from app.extraction.confidence import quality_assessor


@dataclass
class CandidateFinding:
    """Represents a located candidate in document text with positional context and token-level OCR metrics."""
    raw_value: Optional[str]
    all_candidates: List[str] = field(default_factory=list)
    page_number: Optional[int] = None
    extraction_method: Optional[str] = None
    raw_ocr_confidence: Optional[float] = None
    evidence_location: Optional[str] = None
    evidence_snippet: Optional[str] = None
    has_label_match: bool = False
    is_exact_label: bool = False
    is_unreadable: bool = False
    # Word-level OCR token associations
    matched_value_tokens: List[OcrToken] = field(default_factory=list)
    matched_label_tokens: List[OcrToken] = field(default_factory=list)
    field_ocr_confidence: Optional[float] = None
    label_ocr_confidence: Optional[float] = None
    has_token_level_confidence: bool = False


class DocumentParser:
    """Extracts structured fields from OCR page results for a specific category schema."""

    def parse(
        self,
        document_id: str,
        category: str,
        ocr_result: OcrDocumentResult,
    ) -> Dict[str, ExtractedField]:
        """Parses document pages into structured fields with evidence quality assessment."""
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

        # 1. gstin
        gstin_finding = self._find_labeled_then_regex(
            ocr=ocr,
            labels=[r"Registration Number \(GSTIN\)", r"GSTIN", r"Goods and Services Tax Identification Number", r"Tax ID", r"PAN", r"EIN"],
            regex_pattern=r"(?:^|[^A-Z0-9])([0-9O]{2}[A-Z]{5}[0-9O]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})(?:$|[^A-Z0-9])",
            fallback_pattern=r"(?:Tax ID|PAN|EIN)[:\s]+([A-Z0-9\-]+)",
        )
        norm_gstin = normalize_gstin(gstin_finding.raw_value)
        fields["gstin"] = self._create_field(
            field_name="gstin",
            doc_id=document_id,
            finding=gstin_finding,
            norm_record=norm_gstin,
        )

        # 2. legal_entity_name
        name_finding = self._find_labeled_value(
            ocr=ocr,
            labels=[r"Legal Name", r"Name of Business", r"Name of Taxpayer", r"Legal Entity Name", r"Trade Name"],
        )
        norm_name = normalize_entity_name(name_finding.raw_value)
        fields["legal_entity_name"] = self._create_field(
            field_name="legal_entity_name",
            doc_id=document_id,
            finding=name_finding,
            norm_record=norm_name,
        )

        # 3. registration_date
        date_finding = self._find_labeled_value(
            ocr=ocr,
            labels=[r"Date of Registration", r"Registration Date", r"Date of Liability", r"Period of Validity from"],
        )
        norm_date = normalize_date(date_finding.raw_value)
        fields["registration_date"] = self._create_field(
            field_name="registration_date",
            doc_id=document_id,
            finding=date_finding,
            norm_record=norm_date,
        )

        # 4. registered_address
        addr_finding = self._find_labeled_value(
            ocr=ocr,
            labels=[r"Principal Place of Business", r"Registered Address", r"Address of Business", r"Address"],
        )
        norm_addr = normalize_address(addr_finding.raw_value)
        fields["registered_address"] = self._create_field(
            field_name="registered_address",
            doc_id=document_id,
            finding=addr_finding,
            norm_record=norm_addr,
        )

        return fields

    # -------------------------------------------------------------------------
    # 2. BANK PROOF
    # -------------------------------------------------------------------------
    def _parse_bank_proof(self, document_id: str, ocr: OcrDocumentResult) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}

        # 1. account_holder_name
        name_finding = self._find_labeled_value(
            ocr=ocr,
            labels=[r"Account Holder(?: Name)?", r"Customer Name", r"Account Name", r"Beneficiary Name", r"Name"],
        )
        norm_name = normalize_entity_name(name_finding.raw_value)
        fields["account_holder_name"] = self._create_field(
            field_name="account_holder_name",
            doc_id=document_id,
            finding=name_finding,
            norm_record=norm_name,
        )

        # 2. bank_name
        bank_finding = self._find_known_bank_or_label(ocr=ocr)
        norm_bank = normalize_entity_name(bank_finding.raw_value)
        fields["bank_name"] = self._create_field(
            field_name="bank_name",
            doc_id=document_id,
            finding=bank_finding,
            norm_record=norm_bank,
        )

        # 3. account_number
        acc_finding = self._find_labeled_then_regex(
            ocr=ocr,
            labels=[r"Account Number", r"A/c No\.?", r"Account No\.?", r"Account #"],
            regex_pattern=r"(?:^|[^0-9])(\d{9,18})(?:$|[^0-9])",
        )
        norm_acc = normalize_account_number(acc_finding.raw_value)
        fields["account_number"] = self._create_field(
            field_name="account_number",
            doc_id=document_id,
            finding=acc_finding,
            norm_record=norm_acc,
        )

        # 4. ifsc_code
        ifsc_finding = self._find_labeled_then_regex(
            ocr=ocr,
            labels=[r"IFSC Code", r"IFSC", r"Routing Number", r"RTN"],
            regex_pattern=r"(?:^|[^A-Z0-9])([A-Z]{4}0[A-Z0-9]{6})(?:$|[^A-Z0-9])",
        )
        norm_ifsc = normalize_ifsc(ifsc_finding.raw_value)
        fields["ifsc_code"] = self._create_field(
            field_name="ifsc_code",
            doc_id=document_id,
            finding=ifsc_finding,
            norm_record=norm_ifsc,
        )

        return fields

    # -------------------------------------------------------------------------
    # 3. CERTIFICATE OF INCORPORATION
    # -------------------------------------------------------------------------
    def _parse_incorporation_certificate(self, document_id: str, ocr: OcrDocumentResult) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}

        # 1. company_name
        name_finding = self._find_labeled_value(
            ocr=ocr,
            labels=[r"Corporate Name", r"Company Name", r"Name of the Company", r"hereby certifies that", r"Entity Name"],
        )
        norm_name = normalize_entity_name(name_finding.raw_value)
        fields["company_name"] = self._create_field(
            field_name="company_name",
            doc_id=document_id,
            finding=name_finding,
            norm_record=norm_name,
        )

        # 2. cin_or_reg_number
        reg_finding = self._find_labeled_then_regex(
            ocr=ocr,
            labels=[r"Corporate Identity Number", r"CIN", r"Registration Number", r"Company Number", r"Entity Number"],
            regex_pattern=r"(?:^|[^A-Z0-9])([LUu][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6})(?:$|[^A-Z0-9])",
            fallback_pattern=r"(?:^|[^A-Z0-9])([0-9]{7,10})(?:$|[^A-Z0-9])",
        )
        clean_reg = self._clean_str(reg_finding.raw_value)
        norm_reg = NormalizationRecord(
            raw_value=reg_finding.raw_value,
            normalized_value=clean_reg,
            masked_value=clean_reg,
            is_valid_format=bool(clean_reg and len(clean_reg) >= 5),
        )
        fields["cin_or_reg_number"] = self._create_field(
            field_name="cin_or_reg_number",
            doc_id=document_id,
            finding=reg_finding,
            norm_record=norm_reg,
        )

        # 3. incorporation_date
        date_finding = self._find_labeled_value(
            ocr=ocr,
            labels=[r"Date of Incorporation", r"Incorporated on", r"Date of Registration", r"Dated this"],
        )
        norm_date = normalize_date(date_finding.raw_value)
        fields["incorporation_date"] = self._create_field(
            field_name="incorporation_date",
            doc_id=document_id,
            finding=date_finding,
            norm_record=norm_date,
        )

        return fields

    # -------------------------------------------------------------------------
    # 4. ADDRESS PROOF
    # -------------------------------------------------------------------------
    def _parse_address_proof(self, document_id: str, ocr: OcrDocumentResult) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}

        # 1. resident_or_entity_name
        name_finding = self._find_labeled_value(
            ocr=ocr,
            labels=[r"Consumer Name", r"Customer Name", r"Account Holder", r"Billed To", r"Name"],
        )
        norm_name = normalize_entity_name(name_finding.raw_value)
        fields["resident_or_entity_name"] = self._create_field(
            field_name="resident_or_entity_name",
            doc_id=document_id,
            finding=name_finding,
            norm_record=norm_name,
        )

        # 2. full_address
        addr_finding = self._find_labeled_value(
            ocr=ocr,
            labels=[r"Premises Address", r"Service Address", r"Billing Address", r"Address", r"Supply Address"],
        )
        norm_addr = normalize_address(addr_finding.raw_value)
        fields["full_address"] = self._create_field(
            field_name="full_address",
            doc_id=document_id,
            finding=addr_finding,
            norm_record=norm_addr,
        )

        # 3. issue_date
        date_finding = self._find_labeled_value(
            ocr=ocr,
            labels=[r"Bill Date", r"Invoice Date", r"Date of Issue", r"Statement Date", r"Date"],
        )
        norm_date = normalize_date(date_finding.raw_value)
        fields["issue_date"] = self._create_field(
            field_name="issue_date",
            doc_id=document_id,
            finding=date_finding,
            norm_record=norm_date,
        )

        return fields

    # -------------------------------------------------------------------------
    # 5. GENERIC / FALLBACK
    # -------------------------------------------------------------------------
    def _parse_generic(self, document_id: str, ocr: OcrDocumentResult) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}

        name_finding = self._find_labeled_value(ocr=ocr, labels=[r"Name", r"Legal Name", r"Entity"])
        norm_name = normalize_entity_name(name_finding.raw_value)
        fields["entity_name"] = self._create_field(
            field_name="entity_name",
            doc_id=document_id,
            finding=name_finding,
            norm_record=norm_name,
        )

        date_finding = self._find_labeled_value(ocr=ocr, labels=[r"Date", r"Issue Date", r"Document Date"])
        norm_date = normalize_date(date_finding.raw_value)
        fields["document_date"] = self._create_field(
            field_name="document_date",
            doc_id=document_id,
            finding=date_finding,
            norm_record=norm_date,
        )

        return fields

    # -------------------------------------------------------------------------
    # DISCOVERY & EVIDENCE EXTRACTION HELPERS
    # -------------------------------------------------------------------------
    def _find_labeled_value(
        self,
        ocr: OcrDocumentResult,
        labels: List[str],
    ) -> CandidateFinding:
        """Finds candidate value explicitly associated with an expected label."""
        for label_idx, label in enumerate(labels):
            is_exact = (label_idx == 0)
            pattern_inline = re.compile(rf"(?:{label})\s*[:\-=|]\s*(.+)", re.IGNORECASE)
            pattern_label_only = re.compile(rf"(?:{label})\s*[:\-=|]?", re.IGNORECASE)

            for page in ocr.pages:
                for line_idx, line in enumerate(page.lines):
                    # Check inline match
                    m = pattern_inline.search(line)
                    if m:
                        val = self._clean_str(m.group(1))
                        if val and len(val) > 1 and not re.match(r"^[_.\-]{2,}$", val):
                            loc = f"Page {page.page_number}, Line {line_idx + 1}"
                            snip = line[:120]
                            val_toks, lbl_toks, val_c, lbl_c, has_tok = self._associate_tokens(page, val, label)
                            return CandidateFinding(
                                raw_value=val,
                                all_candidates=[val],
                                page_number=page.page_number,
                                extraction_method=page.extraction_method,
                                raw_ocr_confidence=page.confidence,
                                evidence_location=loc,
                                evidence_snippet=snip,
                                has_label_match=True,
                                is_exact_label=is_exact,
                                matched_value_tokens=val_toks,
                                matched_label_tokens=lbl_toks,
                                field_ocr_confidence=val_c,
                                label_ocr_confidence=lbl_c,
                                has_token_level_confidence=has_tok,
                            )
                        elif not val or re.match(r"^[_.\-]{2,}$", val):
                            # Label exists but value is empty or obscured
                            return CandidateFinding(
                                raw_value=None,
                                page_number=page.page_number,
                                extraction_method=page.extraction_method,
                                raw_ocr_confidence=page.confidence,
                                evidence_location=f"Page {page.page_number}, Line {line_idx + 1}",
                                evidence_snippet=line[:120],
                                has_label_match=True,
                                is_exact_label=is_exact,
                                is_unreadable=True,
                            )

                # Check multi-line match (label on current line, value on next line)
                for line_idx in range(len(page.lines) - 1):
                    curr_line = page.lines[line_idx].strip()
                    if pattern_label_only.fullmatch(curr_line):
                        next_line = self._clean_str(page.lines[line_idx + 1])
                        if next_line and len(next_line) > 1 and not re.match(r"^[_.\-]{2,}$", next_line):
                            loc = f"Page {page.page_number}, Lines {line_idx + 1}-{line_idx + 2}"
                            snip = f"{curr_line}: {next_line}"[:120]
                            val_toks, lbl_toks, val_c, lbl_c, has_tok = self._associate_tokens(page, next_line, curr_line)
                            return CandidateFinding(
                                raw_value=next_line,
                                all_candidates=[next_line],
                                page_number=page.page_number,
                                extraction_method=page.extraction_method,
                                raw_ocr_confidence=page.confidence,
                                evidence_location=loc,
                                evidence_snippet=snip,
                                has_label_match=True,
                                is_exact_label=is_exact,
                                matched_value_tokens=val_toks,
                                matched_label_tokens=lbl_toks,
                                field_ocr_confidence=val_c,
                                label_ocr_confidence=lbl_c,
                                has_token_level_confidence=has_tok,
                            )
                        else:
                            # Label detected on line, but next line is unreadable or empty
                            return CandidateFinding(
                                raw_value=None,
                                page_number=page.page_number,
                                extraction_method=page.extraction_method,
                                raw_ocr_confidence=page.confidence,
                                evidence_location=f"Page {page.page_number}, Line {line_idx + 1}",
                                evidence_snippet=curr_line[:120],
                                has_label_match=True,
                                is_exact_label=is_exact,
                                is_unreadable=True,
                            )

        # Genuinely absent
        return CandidateFinding(raw_value=None)

    def _find_labeled_then_regex(
        self,
        ocr: OcrDocumentResult,
        labels: List[str],
        regex_pattern: str,
        fallback_pattern: Optional[str] = None,
    ) -> CandidateFinding:
        """First searches adjacent to labels; falls back to full-page regex scans while counting competing candidates."""
        # 1. Try labeled discovery first
        labeled_res = self._find_labeled_value(ocr, labels)
        if labeled_res.raw_value:
            # Check if there are other candidates in document
            all_cands = self._find_all_regex_candidates(ocr, regex_pattern)
            if labeled_res.raw_value not in all_cands:
                all_cands.append(labeled_res.raw_value)
            labeled_res.all_candidates = list(set(all_cands))
            return labeled_res

        if labeled_res.is_unreadable:
            return labeled_res

        # 2. Fall back to regex scan across all lines
        all_matches = self._find_all_regex_matches_with_context(ocr, regex_pattern)
        if not all_matches and fallback_pattern:
            all_matches = self._find_all_regex_matches_with_context(ocr, fallback_pattern)

        if not all_matches:
            return CandidateFinding(raw_value=None)

        # Primary candidate is the first match
        first = all_matches[0]
        unique_vals = list({m["val"] for m in all_matches})

        return CandidateFinding(
            raw_value=first["val"],
            all_candidates=unique_vals,
            page_number=first["page_number"],
            extraction_method=first["extraction_method"],
            raw_ocr_confidence=first["confidence"],
            evidence_location=first["location"],
            evidence_snippet=first["snippet"],
            has_label_match=False,
            is_exact_label=False,
            matched_value_tokens=first.get("val_tokens", []),
            field_ocr_confidence=first.get("val_conf"),
            has_token_level_confidence=first.get("has_token_conf", False),
        )

    def _find_all_regex_candidates(self, ocr: OcrDocumentResult, pattern: str) -> List[str]:
        regex = re.compile(pattern, re.IGNORECASE)
        cands = []
        for page in ocr.pages:
            for line in page.lines:
                for match in regex.finditer(line):
                    val = match.group(1) if match.groups() else match.group(0)
                    cleaned = self._clean_str(val)
                    if cleaned:
                        cands.append(cleaned)
        return list(set(cands))

    def _find_all_regex_matches_with_context(self, ocr: OcrDocumentResult, pattern: str) -> List[dict]:
        regex = re.compile(pattern, re.IGNORECASE)
        matches = []
        for page in ocr.pages:
            for line_idx, line in enumerate(page.lines):
                for match in regex.finditer(line):
                    val = match.group(1) if match.groups() else match.group(0)
                    cleaned = self._clean_str(val)
                    if cleaned:
                        val_toks, _, val_c, _, has_tok = self._associate_tokens(page, cleaned)
                        matches.append({
                            "val": cleaned,
                            "page_number": page.page_number,
                            "extraction_method": page.extraction_method,
                            "confidence": page.confidence,
                            "location": f"Page {page.page_number}, Line {line_idx + 1}",
                            "snippet": line[:120],
                            "val_tokens": val_toks,
                            "val_conf": val_c,
                            "has_token_conf": has_tok,
                        })
        return matches

    def _find_known_bank_or_label(self, ocr: OcrDocumentResult) -> CandidateFinding:
        known_banks = [
            "HDFC Bank", "ICICI Bank", "State Bank of India", "SBI", "Axis Bank",
            "Kotak Mahindra Bank", "Citibank", "JPMorgan Chase", "Bank of America",
            "Wells Fargo", "Barclays", "Standard Chartered", "HSBC"
        ]
        for page in ocr.pages:
            for line_idx, line in enumerate(page.lines):
                for b in known_banks:
                    if re.search(r"\b" + re.escape(b) + r"\b", line, re.IGNORECASE):
                        loc = f"Page {page.page_number}, Line {line_idx + 1}"
                        snip = line[:120]
                        val_toks, _, val_c, _, has_tok = self._associate_tokens(page, b, b)
                        return CandidateFinding(
                            raw_value=b,
                            all_candidates=[b],
                            page_number=page.page_number,
                            extraction_method=page.extraction_method,
                            raw_ocr_confidence=page.confidence,
                            evidence_location=loc,
                            evidence_snippet=snip,
                            has_label_match=True,
                            is_exact_label=True,
                            matched_value_tokens=val_toks,
                            field_ocr_confidence=val_c,
                            has_token_level_confidence=has_tok,
                        )

        # Fall back to labeled discovery
        return self._find_labeled_value(
            ocr=ocr,
            labels=[r"Bank Name", r"Bank / Branch", r"Financial Institution", r"Bank"]
        )

    def _create_field(
        self,
        field_name: str,
        doc_id: str,
        finding: CandidateFinding,
        norm_record: NormalizationRecord,
    ) -> ExtractedField:
        """Constructs an ExtractedField with full explainability, normalization notes, and provenance."""
        # 1. Unreadable field
        if finding.is_unreadable:
            assessment = quality_assessor.evaluate_field(
                field_name=field_name,
                value=None,
                extraction_method=finding.extraction_method,
                raw_ocr_confidence=finding.raw_ocr_confidence,
                has_label_match=finding.has_label_match,
                is_exact_label=finding.is_exact_label,
                is_valid_format=False,
                is_ambiguous=False,
                was_repaired=False,
                repaired_notes=[],
                candidate_count=0,
                has_page=bool(finding.page_number),
                has_location=bool(finding.evidence_location),
                has_snippet=bool(finding.evidence_snippet),
                is_unreadable=True,
            )
            return ExtractedField(
                field_name=field_name,
                value=None,
                masked_value=None,
                status=FieldStatus.UNREADABLE,
                quality_score=assessment.quality_score,
                confidence=assessment.quality_score,
                quality_breakdown=assessment.breakdown,
                quality_explanation=assessment.explanation,
                normalization_notes=None,
                source=FieldSource(
                    document_id=doc_id,
                    page_number=finding.page_number,
                    extraction_method=finding.extraction_method,
                    evidence_location=finding.evidence_location,
                    evidence_snippet=finding.evidence_snippet,
                ),
                limitation_or_reason=assessment.explanation,
            )

        # 2. Missing field
        if not norm_record.normalized_value:
            assessment = quality_assessor.evaluate_field(
                field_name=field_name,
                value=None,
                extraction_method=None,
                raw_ocr_confidence=None,
                has_label_match=False,
                is_exact_label=False,
                is_valid_format=False,
                is_ambiguous=False,
                was_repaired=False,
                repaired_notes=[],
                candidate_count=0,
                has_page=False,
                has_location=False,
                has_snippet=False,
            )
            return ExtractedField(
                field_name=field_name,
                value=None,
                masked_value=None,
                status=FieldStatus.MISSING,
                quality_score=0.0,
                confidence=0.0,
                quality_breakdown=assessment.breakdown,
                quality_explanation=assessment.explanation,
                normalization_notes=None,
                source=None,  # STRICT INTEGRITY: No fabricated page 1 or DIGITAL_TEXT!
                limitation_or_reason="Field not detected in document content.",
            )

        # 3. Candidate exists (EXTRACTED or NEEDS_REVIEW)
        candidate_count = len(finding.all_candidates) if finding.all_candidates else 1
        assessment = quality_assessor.evaluate_field(
            field_name=field_name,
            value=norm_record.normalized_value,
            extraction_method=finding.extraction_method,
            raw_ocr_confidence=finding.raw_ocr_confidence,
            field_ocr_confidence=finding.field_ocr_confidence,
            has_token_level_confidence=finding.has_token_level_confidence,
            has_label_match=finding.has_label_match,
            is_exact_label=finding.is_exact_label,
            is_valid_format=norm_record.is_valid_format,
            is_ambiguous=norm_record.is_ambiguous,
            was_repaired=norm_record.was_repaired,
            repaired_notes=norm_record.repaired_chars,
            candidate_count=candidate_count,
            has_page=bool(finding.page_number),
            has_location=bool(finding.evidence_location),
            has_snippet=bool(finding.evidence_snippet),
        )

        source = FieldSource(
            document_id=doc_id,
            page_number=finding.page_number,
            extraction_method=finding.extraction_method,
            evidence_location=finding.evidence_location,
            evidence_snippet=finding.evidence_snippet,
        )

        limitation_reason = (
            "; ".join(assessment.reasons_for_review)
            if assessment.reasons_for_review
            else None
        )

        return ExtractedField(
            field_name=field_name,
            value=norm_record.normalized_value,
            masked_value=norm_record.masked_value or norm_record.normalized_value,
            status=assessment.status,
            quality_score=assessment.quality_score,
            confidence=assessment.quality_score,
            quality_breakdown=assessment.breakdown,
            quality_explanation=assessment.explanation,
            normalization_notes=norm_record.summary_note,
            source=source,
            limitation_or_reason=limitation_reason,
        )

    def _clean_str(self, raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        v = re.sub(r"^[\s:\-=|/]+|[\s:\-=|/]+$", "", raw)
        clean = re.sub(r"\s+", " ", v).strip()
        return clean if clean else None

    def _associate_tokens(
        self,
        page: Optional[OcrPageResult],
        raw_val: Optional[str],
        label_text: Optional[str] = None,
    ) -> Tuple[List[OcrToken], List[OcrToken], Optional[float], Optional[float], bool]:
        """Associates OCR tokens with raw extracted value and label.
        
        Returns:
            Tuple[val_tokens, label_tokens, val_conf, label_conf, has_token_confidence]
        """
        if not page or not page.tokens or not raw_val:
            return [], [], None, None, False

        val_tokens = self._find_tokens_for_text(page.tokens, raw_val)
        label_tokens = self._find_tokens_for_text(page.tokens, label_text) if label_text else []

        val_conf = (
            round(sum(t.confidence for t in val_tokens) / len(val_tokens), 2)
            if val_tokens
            else None
        )
        label_conf = (
            round(sum(t.confidence for t in label_tokens) / len(label_tokens), 2)
            if label_tokens
            else None
        )
        has_token_conf = bool(val_tokens)

        return val_tokens, label_tokens, val_conf, label_conf, has_token_conf

    def _find_tokens_for_text(self, page_tokens: List[OcrToken], text: str) -> List[OcrToken]:
        """Matches a target text to OCR tokens using word-level alignment."""
        if not text or not page_tokens:
            return []

        words = re.findall(r"[A-Za-z0-9]+", text.lower())
        if not words:
            return []

        # 1. Contiguous subsequence search
        n_words = len(words)
        for i in range(len(page_tokens) - n_words + 1):
            match = True
            for j in range(n_words):
                token_word = re.sub(r"[^A-Za-z0-9]", "", page_tokens[i + j].text.lower())
                if token_word != words[j]:
                    match = False
                    break
            if match:
                return page_tokens[i : i + n_words]

        # 2. If single word or short token, check individual token contains
        if n_words == 1:
            target = words[0]
            for tok in page_tokens:
                clean_tok = re.sub(r"[^A-Za-z0-9]", "", tok.text.lower())
                if target in clean_tok or clean_tok in target:
                    return [tok]

        # 3. Find any tokens whose text matches the words
        matched = []
        words_set = set(words)
        for tok in page_tokens:
            clean_tok = re.sub(r"[^A-Za-z0-9]", "", tok.text.lower())
            if clean_tok in words_set:
                matched.append(tok)
        return matched


document_parser = DocumentParser()
