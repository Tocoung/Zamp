"""Rule definitions, keyword patterns, and signal weights for document classification."""

from typing import Dict, List, Any


# Primary high-discriminating headings and phrases (heavy weight: +0.45 per match)
CATEGORY_STRONG_HEADINGS: Dict[str, List[str]] = {
    "CERTIFICATE_OF_INCORPORATION": [
        "certificate of incorporation",
        "articles of incorporation",
        "articles of organization",
        "memorandum of association",
        "registrar of companies",
        "commercial register",
        "corporate registration certificate",
        "certificate of registration",
        "corporate affairs",
        "companies act",
        "corporate identity number",
        "incorporation document",
    ],
    "TAX_CERTIFICATE": [
        "goods and services tax",
        "gst registration",
        "form gst reg",
        "taxpayer identification",
        "internal revenue service",
        "department of revenue",
        "inland revenue",
        "hmrc",
        "vat registration certificate",
        "value added tax",
        "form w-9",
        "form w-8ben",
        "tax residency certificate",
        "income tax department",
        "permanent account number",
    ],
    "BANK_PROOF": [
        "bank statement",
        "account statement",
        "voided cheque",
        "cancelled cheque",
        "bank confirmation letter",
        "account verification letter",
        "direct deposit authorization",
        "bank account details",
        "electronic funds transfer",
        "clearing house",
    ],
    "ADDRESS_PROOF": [
        "utility bill",
        "electricity bill",
        "water bill",
        "gas bill",
        "telephone bill",
        "broadband bill",
        "lease agreement",
        "rental agreement",
        "tenancy agreement",
        "certificate of residency",
        "property tax receipt",
    ],
}

# Secondary contextual keywords and domain terms (moderate weight: +0.12 per match)
CATEGORY_CONTEXT_KEYWORDS: Dict[str, List[str]] = {
    "CERTIFICATE_OF_INCORPORATION": [
        "hereby certify that",
        "incorporated on",
        "incorporated under",
        "private limited",
        "limited liability",
        "body corporate",
        "seal of the company",
        "authorized share capital",
        "allotment of shares",
        "registered office of the company",
        "statutory declaration",
        "cin",
        "crn",
    ],
    "TAX_CERTIFICATE": [
        "gstin",
        "tax identification number",
        "tin",
        "ein",
        "pan number",
        "taxpayer",
        "tax period",
        "taxable person",
        "assessing officer",
        "withholding tax",
        "sales tax",
        "vat number",
        "excise duty",
    ],
    "BANK_PROOF": [
        "account holder",
        "routing number",
        "ifsc code",
        "sort code",
        "iban",
        "swift",
        "bic code",
        "opening balance",
        "closing balance",
        "debit",
        "credit",
        "ledger balance",
        "savings account",
        "current account",
        "checking account",
        "branch code",
    ],
    "ADDRESS_PROOF": [
        "service address",
        "billing address",
        "supply address",
        "meter number",
        "consumer number",
        "bill period",
        "due date",
        "landlord",
        "tenant",
        "premises",
        "residential address",
        "proof of address",
        "power distribution",
    ],
}

# Filename tokens (minor secondary signal: +0.08, capped; NEVER confident on its own)
CATEGORY_FILENAME_SIGNALS: Dict[str, List[str]] = {
    "CERTIFICATE_OF_INCORPORATION": [
        "incorporation", "coi", "inc_cert", "company_reg", "articles", "memorandum"
    ],
    "TAX_CERTIFICATE": [
        "gst", "pan", "w9", "w8", "vat", "tax_cert", "tax_return", "tax_id"
    ],
    "BANK_PROOF": [
        "bank_statement", "cheque", "check", "bank_proof", "voided", "statement", "passbook"
    ],
    "ADDRESS_PROOF": [
        "utility", "electricity", "water_bill", "lease", "rent", "address_proof", "telecom"
    ],
}
