# Zamp — AI-Powered Vendor Onboarding Automation

> **Case Study:** Zamp AI Solutions Analyst Case Study  
> **Phase:** 2 (Step 4 — Extraction Confidence & Evidence Management)  
> **Status:** Fully Integrated, Tested, and Verified (195 Automated Tests Passing)  

An automated platform designed to streamline vendor company onboarding, compliance document intake & secure storage, multi-source verification, deterministic validation, explainable decisioning (`APPROVED` / `PENDING` / `REJECTED`), lifecycle activity tracking, and human-in-the-loop review.

---

## 1. Architecture & Technology Stack

The project uses a clean **Modular Monolith** architecture with decoupled presentation, validation, decision, document storage, activity, and service layers:

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + Lucide React (Vendor intake form, vendor directory, full profile inspection, decision explanation, in-modal edit/correction mode, chronological activity timeline, supporting documents manager, document classifier, structured extraction drawer with field provenance, quality score badges, signal breakdowns, and original document page preview inspection modal)
- **Backend:** Python 3.9+ + FastAPI + Pydantic v2 + Uvicorn + Cryptography (Fernet authenticated encryption at rest) + Tesseract OCR + Poppler + Pypdf
- **Document Intake & Secure Storage:** Dedicated storage service (`backend/app/core/storage.py`) and validator (`backend/app/core/document_validator.py`) enforcing magic-byte inspection, bounded chunked streaming, atomic `.tmp` writes, path traversal prevention, authenticated symmetric encryption at rest (Fernet AES-128-CBC + HMAC-SHA256), and SHA-256 integrity checksums.
- **Document Classification Engine:** Explainable rule-based categorization (`backend/app/classification/`) identifying document types (`TAX_CERTIFICATE`, `BANK_PROOF`, etc.) with transparent heuristic match scores and limitation codes.
- **OCR & Structured Extraction Pipeline:** End-to-end multi-format text recognition and field extraction (`backend/app/extraction/`) supporting digital PDFs, scanned PDFs (rasterized page rendering + OCR), and standalone images (PNG/JPEG) with field-level provenance and PII masking.
- **Extraction Confidence & Evidence Inspection:** Explainable quality assessment (`backend/app/extraction/confidence.py`), robust canonical normalization (`backend/app/extraction/normalization.py`), distinct field statuses (`EXTRACTED`, `NEEDS_REVIEW`, `MISSING`, `UNREADABLE`), in-memory page preview streaming (`GET .../pages/{page}/preview`), and strict non-mutation data integrity guarantees.
- **Validation Engine:** Modular, decoupled rule engine (`backend/app/validation/`) evaluating 28 deterministic rules across required fields, country-aware statutory formats, and cross-field consistency.
- **Decision Engine:** Deterministic business policy and explainability engine (`backend/app/decision/`) assigning `APPROVED`, `PENDING`, or `REJECTED` outcomes with stable reason codes and actionable recommendations.
- **Activity & Lifecycle History:** Dedicated `vendor_activities` table tracking discrete lifecycle events (`VENDOR_SUBMITTED`, `DECISION_EXECUTED`, `VENDOR_UPDATED`, `DECISION_REEVALUATED`, `DOCUMENT_UPLOADED`, `DOCUMENT_DELETED`, `DOCUMENT_CLASSIFIED`, `DOCUMENT_EXTRACTED`) in deterministic chronological order with zero sensitive financial data leakage.
- **Persistence:** SQLAlchemy 2.0 (Active: SQLite with deterministic path resolution; Production interface: PostgreSQL via `DATABASE_URL` with driver).
- **Audit History:** Dedicated `vendor_decisions`, `vendor_documents`, `document_classifications`, and `document_extractions` tables preserving immutable audit records transactionally.
- **Testing:** Pytest + FastAPI TestClient with temporary isolated SQLite databases and isolated storage directories (**195 automated tests passing**).

Detailed architectural boundaries and module roadmaps can be found in [docs/architecture.md](docs/architecture.md).

---

## 2. Decision Engine & Policy Hardening (Step 4 & Step 4.1)

The decision engine resides in `backend/app/decision/` and service layer `backend/app/services/decision_service.py`. It is a deterministic business rules engine, not an AI/LLM classifier.

### A. Core Architecture & Separation of Concerns
- **`models.py`:** Pydantic schemas for `DecisionStatus` (`APPROVED`, `PENDING`, `REJECTED`), `DecisionAction` (`BLOCK`, `REVIEW`, `IGNORE`), `DecisionReason`, `DecisionRecommendation`, `DecisionResult`, and `DecisionHistoryItem`.
- **`config.py`:** Configurable action mappings (`rule_actions`, `finding_code_actions`), severity fallbacks, programmatically verified registry coverage (`verify_registry_coverage()`), and independent decision versioning (`decision_version: "1.0.0"`).
- **`rules.py`:** Evaluates validation findings into explainable reasons and actionable next steps without exposing sensitive financial details or reflecting raw user inputs.
- **`engine.py`:** Orchestrates decision calculation from a single `ValidationResult` snapshot, applies policy thresholds, sorts findings deterministically, and sanitizes evidence.
- **`registry.py`:** Singleton registry providing global access and test isolation.
- **`services/decision_service.py`:** Manages transactional persistence: safely decrypts banking data in memory, runs validation exactly once, calculates the decision, updates vendor status, and records audit history. If decryption or key failures occur, execution aborts cleanly with zero database mutations.

### B. Status Semantics & Decision Outcomes

| Status | Business Criteria | Operational Meaning |
|---|---|---|
| **`APPROVED`** | Validation is `PASSED`, 0 `ERROR` findings, 0 `WARNING` findings requiring review, all mandatory checks satisfied. | All deterministic statutory formats and company consistency rules passed. *Note:* Deterministic local check only; does not claim independent tax authority verification or banking ownership guarantee. |
| **`PENDING`** | Missing mandatory submission fields or discrepancies requiring review (e.g. account holder name mismatch, tax-country mismatch). | Vendor submission is incomplete or needs review, but is not conclusively invalid. Incomplete information is **never** treated as fraud or ineligibility; actionable recommendations request the missing data. |
| **`REJECTED`** | Validation `ERROR` mapped to configured blocking reason (e.g. invalid GSTIN/PAN/EIN syntax, invalid email format, invalid routing transit code or checksum, dummy bank account sequence). | Statutory format or structural banking requirements were conclusively violated. Formatting errors are reported as syntax failures, not malicious intent. |

### C. Finding to Decision Action Mapping

The engine maps validation rule IDs and finding codes to one of three `DecisionAction` directives:
- **`BLOCK` $\rightarrow$ `REJECTED`:** Hard statutory or structural failure.
- **`REVIEW` $\rightarrow$ `PENDING`:** Discrepancy or incomplete mandatory field requiring clarification or document review.
- **`IGNORE` $\rightarrow$ `APPROVED`:** Informational note that does not impede automated onboarding.

| Validation Finding / Rule ID | Finding Code | Action | Decision | Operational Rationale |
|---|---|---|---|---|
| Missing mandatory field (all 19 rules) | `MISSING_*` / `REQUIRED_FIELD_MISSING` | `REVIEW` | **`PENDING`** | Incomplete submission is not conclusive proof of ineligibility. |
| Invalid contact email format | `INVALID_EMAIL_FORMAT` | `BLOCK` | **`REJECTED`** | Unusable communications channel. |
| Invalid phone format / characters | `INVALID_PHONE_STRUCTURE` / `_DIGIT_COUNT` | `BLOCK` | **`REJECTED`** | Structural telecommunication syntax error. |
| Malformed India GSTIN | `INVALID_GSTIN_FORMAT` | `BLOCK` | **`REJECTED`** | Statutory 15-character tax regex violation. |
| Malformed India PAN | `INVALID_PAN_FORMAT` | `BLOCK` | **`REJECTED`** | Statutory 10-character tax regex violation. |
| Malformed US EIN / invalid prefix | `INVALID_EIN_FORMAT` / `_PREFIX` | `BLOCK` | **`REJECTED`** | Statutory US tax format or unassigned IRS campus prefix. |
| Malformed UK VAT | `INVALID_UK_VAT_FORMAT` | `BLOCK` | **`REJECTED`** | Statutory UK VAT syntax violation. |
| Invalid bank routing / IFSC / SWIFT | `INVALID_*_FORMAT` | `BLOCK` | **`REJECTED`** | Clearing transit code structural violation. |
| US ABA checksum failure | `INVALID_ABA_CHECKSUM` | `BLOCK` | **`REJECTED`** | Failed Federal Reserve Mod-10 checksum algorithm. |
| Dummy account sequence (`00000000`) | `DUMMY_ACCOUNT_SEQUENCE` | `BLOCK` | **`REJECTED`** | Placeholder account sequence rejected. |
| Bank account holder name mismatch | `ACCOUNT_HOLDER_NAME_MISMATCH` | `REVIEW` | **`PENDING`** | Review required for DBA / parent entity documentation. |
| Tax scheme vs. country mismatch | `TAX_TYPE_COUNTRY_MISMATCH` | `REVIEW` | **`PENDING`** | Jurisdictional tax scheme alignment review. |
| Bank routing vs. country mismatch | `ROUTING_BANK_COUNTRY_MISMATCH` | `REVIEW` | **`PENDING`** | Domestic clearing vs. domicile country alignment review. |
| Unusual routing number length | `UNUSUAL_ROUTING_LENGTH` | `REVIEW` | **`PENDING`** | Clearing code length warning for jurisdiction. |
| Cross-border incorporation/address | `CROSS_BORDER_OPERATIONS_NOTE` | `IGNORE` | **`APPROVED`** | Operational informational note (non-blocking). |
| Unsupported tax regime | `TAX_FORMAT_UNSUPPORTED_NOTE` | `IGNORE` | **`APPROVED`** | Foreign tax scheme noted without claiming external verification. |
| All checks pass with 0 warnings | *(None)* | — | **`APPROVED`** | Clean deterministic validation run. |
| Technical Decryption Failure / Key Missing | `EncryptionError` | **Abort** | **`HTTP 500`** | Security failure aborts decision evaluation with zero mutation. |

### D. Audit History & Persistence Model

Decisions are persisted non-destructively in SQLite via the `vendor_decisions` table:
- `id`: UUID (Primary Key).
- `vendor_id`: Foreign key to `vendors.id` (ON DELETE CASCADE).
- `status`: `APPROVED`, `PENDING`, or `REJECTED`.
- `decision_version`: String (`1.0.0`).
- `ruleset_version`: String (`1.0.0` from validation engine).
- `validation_id`: Foreign reference to evaluated validation execution.
- `validation_snapshot`: Sanitized JSON evidence containing check summaries and field findings (**strictly zero raw bank account numbers or ciphertexts**).
- `reason_codes`: JSON array of stable programmatic reason strings (`MISSING_LEGAL_NAME`, `INVALID_GSTIN_FORMAT`, etc.).
- `decision_explanation`: JSON object containing structured reasons and actionable recommendations.
- `decided_at`: UTC timestamp.

**Transactional Guarantee:** `VendorDecision` insertion and `Vendor.status` mutation occur in the same database transaction. If either fails, both roll back.

**Re-evaluation Behaviour:** Multiple decision runs against the same vendor append new audited records to `vendor_decisions` while updating `Vendor.status` to reflect the latest outcome. Previous decisions remain permanently intact.

### E. Decision API Endpoints

- `POST /api/v1/vendors/{vendor_id}/decide`: Runs validation once, evaluates deterministic decision, persists audit record, updates vendor status, and returns `DecisionResult`.
- `GET /api/v1/vendors/{vendor_id}/decision`: Returns the most recent `DecisionResult` for a vendor.
- `GET /api/v1/vendors/{vendor_id}/decision-history`: Returns deterministically paginated decision history (`created_at DESC, id ASC`).
- `GET /api/v1/vendors?status=APPROVED|PENDING|REJECTED|SUBMITTED`: Filters vendor directory by onboarding status.

---

## 3. End-to-End Vendor Onboarding Integration (Step 5)

Phase 1 Step 5 integrates all previous milestones into a unified, operational end-to-end lifecycle:

```
[Vendor Registration Intake]
             |
             v
 [Encrypted Persistence (Fernet)]  ---> [Activity: VENDOR_SUBMITTED]
             |
             v
 [Deterministic Validation Engine]  (Evaluates 28 statutory & consistency rules)
             |
             v
 [Explainable Decision Engine]     (Applies BLOCK/REVIEW/IGNORE policies)
             |
             +---> [Persist Decision Snapshot (vendor_decisions)]
             +---> [Atomic Status Transition (APPROVED | PENDING | REJECTED)]
             +---> [Activity: DECISION_EXECUTED]
             |
   +---------+---------+
   |                   |
[APPROVED]        [PENDING / REJECTED]
   |                   |
   |              [Operator/Vendor Profile Correction via UI]
   |                   |
   |                   v
   |             [Encrypted Update] ---> [Activity: VENDOR_UPDATED]
   |                   |
   |                   v
   |             [Re-evaluation via POST /decide]
   |                   |
   |                   +---> [Append Decision Snapshot to History]
   |                   +---> [Update Status: APPROVED]
   |                   +---> [Activity: DECISION_REEVALUATED]
```

### A. Lifecycle Architecture & Data Flow
1. **Intake & Submission:** Vendor enters identity, address, tax, and banking details. Banking account numbers are encrypted at rest with Fernet (`AES-128-CBC + HMAC-SHA256`) and masked in all responses. The initial record is saved with status `SUBMITTED`, and a `VENDOR_SUBMITTED` activity event is recorded.
2. **On-Demand Validation:** Operators can validate records via `POST /api/v1/vendors/{id}/validate`. The endpoint decrypts banking data strictly in memory, runs validation rules, and returns a detailed finding report without altering vendor status.
3. **Deterministic Decisioning:** Invoking `POST /api/v1/vendors/{id}/decide` computes validation findings once, maps them to `BLOCK`, `REVIEW`, or `IGNORE` actions, determines the outcome (`APPROVED`, `PENDING`, `REJECTED`), persists an immutable audit snapshot in `vendor_decisions`, updates `Vendor.status`, and logs `DECISION_EXECUTED` (or `DECISION_REEVALUATED`).
4. **Interactive Profile Correction:** If a vendor receives `PENDING` (e.g. account holder name mismatch or missing non-blocking fields), compliance operators can switch the detail modal to "Edit / Correct", update the attributes via `PUT /api/v1/vendors/{id}`, and immediately trigger re-evaluation.

### B. Dual-History Architecture: Decision Audit vs. Activity Timeline
To maintain clean separation between compliance audits and operational monitoring:

| Dimension | Decision History (`VendorDecision`) | Activity Timeline (`VendorActivity`) |
|---|---|---|
| **Table** | `vendor_decisions` | `vendor_activities` |
| **Purpose** | Regulatory compliance & explainability audit trail. | Chronological operational lifecycle execution history. |
| **Data Stored** | Full sanitized validation snapshot, stable reason codes, policy explanations, actionable recommendations. | Discrete event classification (`VENDOR_SUBMITTED`, `DECISION_EXECUTED`, `VENDOR_UPDATED`, `DECISION_REEVALUATED`), human-readable title, safe summary, and status snapshot. |
| **Access Patterns** | Query latest decision (`GET /vendors/{id}/decision`) or paginated history (`GET /vendors/{id}/decision-history`). | Paginated chronological event feed (`GET /vendors/{id}/activities?page=1&page_size=20`). |
| **Security** | Zero raw bank accounts or encryption tokens in snapshot. | Zero raw banking data, tax IDs, or cryptographic tokens in descriptions. |

### C. Decryption Failure Hardening across Endpoints
In accordance with Step 2.1 and Step 5 hardening:
- Both `POST /api/v1/vendors/{id}/validate` and `POST /api/v1/vendors/{id}/decide` safely handle cryptographic or key failures.
- If a stored bank account number cannot be decrypted (corrupted ciphertext token, incorrect key), the backend logs a security error and raises `HTTP 500 Internal Server Error` (`Security or data integrity error: Sensitive banking data could not be safely decrypted for validation`).
- The system **never** catches decryption failures and falls back to reporting `bank_account_number` as missing, preventing false validation findings or accidental status corruption.

---

## 4. Synthetic Demonstration Data Seeder

A dedicated seeder script (`backend/app/scripts/seed_demo_data.py`) generates 4 distinct, realistic, and explicitly synthetic demonstration vendors:

| Scenario | Vendor Name | Incorporation | Key Finding / Condition | Expected Outcome |
|---|---|---|---|---|
| **1. Clean Happy Path** | Solaris Tech Labs Private Limited `[DEMO]` | India | All mandatory fields present, valid GSTIN & IFSC, matching bank account holder. | **`APPROVED`** |
| **2. Missing Mandatory Fields** | Nova Dynamics India Pvt Ltd `[DEMO]` | India | Missing mandatory company registration number and contact phone number. | **`PENDING`** (Recommendations request missing data) |
| **3. Consistency Discrepancy** | Zenith Global Logistics LLP `[DEMO]` | India | Bank account holder name (`Zenith Logistics Escrow Agency`) differs from company name. | **`PENDING`** (Recommendations request account ownership verification) |
| **4. Blocking Format Error** | Vortex Industrial Supplies Inc `[DEMO]` | India | Malformed statutory GSTIN syntax (`33INVALID_SYNTAX_999`). | **`REJECTED`** (Recommendations request valid tax certificate) |

### CLI Usage & Flags
```bash
# Seed 4 demo vendors and evaluate their initial decisions (idempotent):
python backend/app/scripts/seed_demo_data.py

# Seed demo vendors in initial SUBMITTED state without running decisions:
python backend/app/scripts/seed_demo_data.py --no-decisions

# Safely reset/remove all demo records without touching real vendor records:
python backend/app/scripts/seed_demo_data.py --reset
```

### End-to-End Live Demonstration Walkthrough
1. **Review Seeded Vendors:** Open `http://localhost:5173` to view the Vendor Directory. Observe the 4 seeded demo vendors categorized by their distinct statuses (`APPROVED`, `PENDING`, `REJECTED`).
2. **Inspect Decision & Activity Timeline:** Click on **Zenith Global Logistics LLP `[DEMO]`**.
   - Review the Decision Banner (`PENDING`), the reason code `ACCOUNT_HOLDER_NAME_MISMATCH`, and actionable recommendations.
   - Inspect the **Lifecycle Activity Timeline** showing `Vendor Registration Submitted` and `Decision Executed`.
3. **Correct Profile & Re-evaluate:**
   - Click **Edit / Correct Profile**.
   - Change Bank Account Holder Name to `Zenith Global Logistics LLP`.
   - Click **Save Changes**. Note the timeline appends `Vendor Profile Updated`.
   - Click **Evaluate Decision**. Observe the status update to **`APPROVED`**.
   - Check Decision Audit History: shows 2 historical decisions (latest `APPROVED`, prior `PENDING`).

---

## 5. Sample Decision Outputs

### A. Approved Vendor (`APPROVED`)
```json
{
  "decision_id": "e852d6db-6459-4cf9-aedc-941de98d50d5",
  "vendor_id": "a550cc4b-08ce-49e9-b49c-c7c84d770753",
  "status": "APPROVED",
  "decision_version": "1.0.0",
  "ruleset_version": "1.0.0",
  "validation_id": "8d3168ae-2bc9-4d21-92e8-416ee2dfea8c",
  "validation_status": "PASSED",
  "reason_codes": [
    "DETERMINISTIC_RULES_PASSED"
  ],
  "reasons": [
    {
      "code": "DETERMINISTIC_RULES_PASSED",
      "title": "All Deterministic Validation Rules Satisfied",
      "explanation": "Vendor data successfully satisfied all mandatory fields, statutory formats, and consistency rules without blocking issues.",
      "severity": "INFO"
    }
  ],
  "recommendations": [
    {
      "action": "PROCEED_WITH_ONBOARDING",
      "description": "Vendor record satisfies all configured deterministic onboarding rules. Proceed with operational setup.",
      "priority": "LOW"
    }
  ],
  "decided_at": "2026-11-21T12:47:23.411196Z"
}
```

### B. Pending Review Vendor (`PENDING` — Sanitized Review Mismatch)
```json
{
  "decision_id": "2a762e8e-2aab-4df2-8930-39dec98069ff",
  "vendor_id": "0a014de4-c63c-4684-b45e-5566d908566c",
  "status": "PENDING",
  "decision_version": "1.0.0",
  "ruleset_version": "1.0.0",
  "validation_status": "PASSED_WITH_WARNINGS",
  "reason_codes": [
    "ACCOUNT_HOLDER_NAME_MISMATCH"
  ],
  "reasons": [
    {
      "code": "ACCOUNT_HOLDER_NAME_MISMATCH",
      "title": "Bank Account Holder Name Requires Review",
      "explanation": "The bank account holder name does not sufficiently match the registered company or trade name.",
      "source_rule_id": "CONST_ACCOUNT_HOLDER_MATCH",
      "severity": "WARNING"
    }
  ],
  "recommendations": [
    {
      "action": "VERIFY_ACCOUNT_HOLDER",
      "description": "Confirm the bank account belongs to the submitted legal entity, or request documentation explaining the DBA or parent company relationship.",
      "priority": "MEDIUM"
    }
  ],
  "decided_at": "2026-11-21T12:48:39.822783Z"
}
```

### C. Incomplete Submission Vendor (`PENDING` — Missing Mandatory Field)
```json
{
  "decision_id": "f471b092-23c1-4cb5-bb50-51b88e14b2d1",
  "vendor_id": "b968de41-657d-411a-a035-7c15e612cb74",
  "status": "PENDING",
  "decision_version": "1.0.0",
  "ruleset_version": "1.0.0",
  "validation_status": "FAILED",
  "reason_codes": [
    "MISSING_LEGAL_NAME"
  ],
  "reasons": [
    {
      "code": "MISSING_LEGAL_NAME",
      "title": "Missing Required Field: Legal Name",
      "explanation": "Mandatory field 'legal_name' is missing or blank. Vendor submission is incomplete.",
      "source_rule_id": "COMPANY_LEGAL_NAME_REQUIRED",
      "severity": "ERROR"
    }
  ],
  "recommendations": [
    {
      "action": "PROVIDE_LEGAL_NAME",
      "description": "Provide a valid value for mandatory field 'legal_name' to complete submission.",
      "priority": "MEDIUM"
    }
  ],
  "decided_at": "2026-11-21T13:30:12.441829Z"
}
```

### D. Rejected Vendor (`REJECTED`)
```json
{
  "decision_id": "d3acec53-3a2c-4e12-a020-12dd875f4481",
  "vendor_id": "0dc03819-badb-4b7e-a05c-f9567521e90b",
  "status": "REJECTED",
  "decision_version": "1.0.0",
  "ruleset_version": "1.0.0",
  "validation_status": "FAILED",
  "reason_codes": [
    "INVALID_GSTIN_FORMAT"
  ],
  "reasons": [
    {
      "code": "INVALID_GSTIN_FORMAT",
      "title": "Statutory GSTIN Format Invalid",
      "explanation": "GSTIN format is invalid. Expected 15-character statutory format (e.g., 29ABCDE1234F1Z5).",
      "source_rule_id": "FMT_TAX_ID_SYNTAX",
      "severity": "ERROR"
    }
  ],
  "recommendations": [
    {
      "action": "VERIFY_TAX_REGISTRATION",
      "description": "Request a verified copy of the vendor's official tax certificate and correct the statutory tax identifier.",
      "priority": "HIGH"
    }
  ],
  "decided_at": "2026-11-21T12:49:12.102806Z"
}
```
      "explanation": "Bank account holder name ('Global Retail Logistics Holdings LLC') does not appear to match legal company name ('Acme Widgets Private Limited').",
      "source_rule_id": "CONST_ACCOUNT_HOLDER_MATCH",
      "severity": "WARNING"
    }
  ],
  "recommendations": [
    {
      "action": "VERIFY_ACCOUNT_HOLDER",
      "description": "Confirm the bank account belongs to the submitted legal entity, or request documentation explaining the DBA or parent company relationship.",
      "priority": "MEDIUM"
    }
  ],
  "decided_at": "2026-11-21T12:48:39.822783Z"
}
```

### C. Rejected Vendor (`REJECTED`)
```json
{
  "decision_id": "d3acec53-3a2c-4e12-a020-12dd875f4481",
  "vendor_id": "0dc03819-badb-4b7e-a05c-f9567521e90b",
  "status": "REJECTED",
  "decision_version": "1.0.0",
  "ruleset_version": "1.0.0",
  "validation_status": "FAILED",
  "reason_codes": [
    "INVALID_GSTIN_FORMAT"
  ],
  "reasons": [
    {
      "code": "INVALID_GSTIN_FORMAT",
      "title": "Statutory GSTIN Format Invalid",
      "explanation": "GSTIN format is invalid. Expected 15-character statutory format (e.g., 29ABCDE1234F1Z5).",
      "source_rule_id": "FMT_TAX_ID_SYNTAX",
      "severity": "ERROR"
    }
  ],
  "recommendations": [
    {
      "action": "VERIFY_TAX_REGISTRATION",
      "description": "Request a verified copy of the vendor's official tax certificate and correct the statutory tax identifier.",
      "priority": "HIGH"
    }
  ],
  "decided_at": "2026-11-21T12:49:12.102806Z"
}
```

---

## 6. Deterministic Validation Engine (Step 3 Recap)

The underlying validation engine resides in `backend/app/validation/`:
- **Ruleset Version:** `1.0.0`
- **28 Active Deterministic Rules:** Mandatory fields, contact formats, India GSTIN/PAN, US EIN with IRS prefix check, UK VAT, India IFSC, US ABA Mod-10 checksum, SWIFT/BIC, bank account length/dummy checks, and cross-field consistency.
- **Privacy:** Evaluates decrypted account numbers in memory without logging or returning raw values in responses.
- **Endpoints:**
  - `POST /api/v1/vendors/validate`: Evaluates unsaved payloads without DB writes.
  - `POST /api/v1/vendors/{vendor_id}/validate`: Evaluates stored vendors without status mutation.

---

## 7. Security & Reliability Architecture (Step 2.1 Recap)

- **Encryption at Rest:** Bank account numbers are encrypted using Fernet (`AES-128-CBC + HMAC-SHA256`).
- **Fail-Safe Startup:** If `VENDOR_DATA_ENCRYPTION_KEY` is missing or invalid, application startup aborts immediately.
- **Masking:** API responses and UI screens only display masked account numbers (`••••••••5678`).
- **Zero Sensitive Data in Decision History:** Raw account numbers are strictly excluded from `validation_snapshot`, decision explanations, and lifecycle activities.

---

## 8. Document Intake & Secure Storage Architecture (Phase 2, Step 1)

Phase 2, Step 1 introduces enterprise multi-document intake and encrypted storage at rest for vendor onboarding artifacts.

### A. Core Architecture & Storage Guarantees
- **Encrypted Blob Storage at Rest:** Files are encrypted with Fernet symmetric authenticated encryption (`AES-128-CBC + HMAC-SHA256`) and stored outside public web roots (`data/documents/`). Internal physical paths and encryption tokens are never returned in public APIs.
- **Path Traversal Prevention:** Storage paths use non-enumerable UUID identifiers (`{vendor_id}/{document_id}.enc`) with containment assertions (`target.relative_to(root)`). Path traversal (`../`) attempts raise `StoragePathTraversalError`.
- **Atomic Writes & Rollback:** Uploaded files write to `.tmp` files before atomic rename. If database persistence fails, disk files are immediately purged and the transaction rolled back.
- **Cryptographic Integrity:** SHA-256 hashes are calculated on unencrypted inputs and verified during retrieval to guarantee file authenticity.

### B. Upload Validation & Defense in Depth
- **Size Limit:** Enforces 10 MB (`10,485,760` bytes) maximum size and rejects 0-byte uploads (`HTTP 413` / `HTTP 400`).
- **File Format Whitelist:** Accepts only `.pdf`, `.png`, `.jpg`, and `.jpeg`.
- **Magic Byte Signature Inspection:** Reads binary headers to confirm true file types:
  - PDF: `%PDF-`
  - PNG: `\x89PNG\r\n\x1a\n`
  - JPEG: `\xFF\xD8\xFF`
  Mismatched extensions or declared MIME headers are rejected with `HTTP 400`.
- **Filename Sanitization:** Path delimiters, null bytes, and traversal tokens are stripped to produce safe display filenames.

### C. Document REST API Endpoints
- `POST /api/v1/vendors/{vendor_id}/documents`: Multipart intake endpoint.
- `GET /api/v1/vendors/{vendor_id}/documents`: Paginated listing with optional `?category=` filter.
- `GET /api/v1/vendors/{vendor_id}/documents/{document_id}`: Metadata retrieval.
- `GET /api/v1/vendors/{vendor_id}/documents/{document_id}/content`: Authenticated decrypted file download stream with `Content-Disposition: attachment; filename="<sanitized>"` and `X-Content-Type-Options: nosniff`.
- `DELETE /api/v1/vendors/{vendor_id}/documents/{document_id}`: Removes metadata and purges ciphertext from disk (`204 No Content`).

### D. Audit Activity Tracking
Every document upload and deletion records an event in `VendorActivity`:
- `DOCUMENT_UPLOADED`: Records filename, category, and formatted byte size.
- `DOCUMENT_DELETED`: Records document deletion without leaking storage keys.

### E. Storage Resource & Lifecycle Hardening (Phase 2, Step 1.1)
- **Bounded Chunked Upload Reading:** Uploads are streamed in bounded 64 KB chunks (`read_upload_file_bounded`). As soon as accumulated payload size exceeds the 10 MB limit, reading halts immediately with `HTTP 413 Payload Too Large` without buffering the remaining payload into RAM. The underlying upload resource is safely closed in all cases.
- **Strict Path Containment & Symlink Defense:** Internal storage paths are strictly normalized to `<vendor_id>/<document_id>.enc` with UUID format assertions. Null bytes (`\x00`), backslashes (`\`), path traversal tokens (`..`), and absolute paths are rejected with `StoragePathTraversalError`. Symlinks escaping the storage root are trapped via realpath verification. Internal server directory structures are masked from error messages.
- **Two-Phase Staged Deletion & Self-Healing Consistency:** Document deletion stages disk files (`.enc` $\to$ `.enc.deleted`) before touching SQLite. If disk staging fails (e.g. read-only filesystem or permissions), the database record is preserved and no `DOCUMENT_DELETED` activity is emitted (`HTTP 500`). If the database transaction fails, the staged `.deleted` file is rolled back to `.enc`. Missing files on disk are handled idempotently.

---

## 9. Document Classification Engine & Explainability (Phase 2, Step 2)

The document classification engine resides in `backend/app/classification/` and service layer `backend/app/services/classification_service.py`. It is a pure, deterministic, rule-based content classifier that analyzes extracted text from digitally readable PDFs.

### A. Architectural Separation & Safety Boundaries
- **Strict Separation of Concerns:** Classification operates independently of the vendor validation and decision engines. Running classification produces an explainable document prediction, but **NEVER alters vendor onboarding status** (`APPROVED`/`PENDING`/`REJECTED`).
- **Preservation of Declared Category:** The category selected by the user/vendor at upload time is preserved as `declared_category`. The classifier predicts `predicted_category` without overwriting the user's input.
- **Safe Internal Digital Text Extraction:** Uses `pypdf` bounded to the first 25 pages and 50,000 characters. No OCR is attempted for scanned images or textless PDFs: image-only uploads (PNG, JPEG) explicitly return `status="INSUFFICIENT_TEXT"` with `limitation_code="IMAGE_ONLY_DOCUMENT"`, and textless PDFs return `limitation_code="NO_EXTRACTABLE_TEXT"`.
- **Zero Sensitive Data Leakage:** Classification evidence records only matched dictionary heading strings and context keyword counts (`matched_headings`, `matched_keywords`, `signals_by_category`). Raw extracted document text and sensitive financial numbers are never stored in the database or exposed via API.

### B. Supported Document Categories
1. **`CERTIFICATE_OF_INCORPORATION`:** Ministry of Corporate Affairs, Certificate of Incorporation, Registrar of Companies, Companies Act, Articles of Association, CIN.
2. **`TAX_CERTIFICATE`:** Form GST REG-06, Registration Certificate, Goods and Services Tax, GSTIN, W-9, Department of the Treasury, Internal Revenue Service, VAT Registration.
3. **`BANK_PROOF`:** Account Statement, Bank Statement, Cancelled Cheque, Voided Cheque, IFSC Code, Account Holder Name, Routing Transit Number.
4. **`ADDRESS_PROOF`:** Electricity Bill, Utility Bill, Municipal Corporation, Consumer Invoice, Premises Address, Proof of Address.
5. **`OTHER`:** Valid supporting documents not fitting standard statutory templates.
6. **`UNKNOWN`:** Submissions with ambiguous or unextractable content.

### C. Deterministic Scoring & Decision Thresholds
- **Heading Matches:** High-weight signals contribute up to 0.70 toward category score.
- **Contextual Keywords:** Supporting terminology contributes up to 0.40.
- **Filename Signals:** Weak secondary hints contribute up to 0.08 (filename alone can never elevate an empty or textless document).
- **Classification Status Logic:**
  - Score $\ge 0.70$ and clear winner $\rightarrow$ `CLASSIFIED`
  - Score between $0.40$ and $0.70$ $\rightarrow$ `LOW_CONFIDENCE`
  - Score $< 0.40$ or ambiguous $\rightarrow$ `LOW_CONFIDENCE` (`predicted_category="UNKNOWN"`)
  - Conflicting top signals (margin $< 0.15$ with both $\ge 0.35$) $\rightarrow$ `LOW_CONFIDENCE` (`limitation_code="CONFLICTING_SIGNALS"`)
  - Non-extractable text $\rightarrow$ `INSUFFICIENT_TEXT` (confidence `0.0`, `limitation_code="NO_EXTRACTABLE_TEXT"` or `"IMAGE_ONLY_DOCUMENT"`)

### D. Audit Persistence & REST API Endpoints
Classifications are stored transactionally in `document_classifications` table and tracked in `vendor_activities` with `DOCUMENT_CLASSIFIED` event:
- `POST /api/v1/vendors/{vendor_id}/documents/{document_id}/classify`: Triggers deterministic content classification and records explainable result.
- `GET /api/v1/vendors/{vendor_id}/documents/{document_id}/classification`: Returns the latest classification result and explainability signals.
- `GET /api/v1/vendors/{vendor_id}/documents/{document_id}/classification-history`: Returns paginated history of all classification runs.
- `GET /api/v1/vendors/{vendor_id}/documents`: Returns document metadata with embedded `latest_classification` object.

---

## 5. OCR & Structured Information Extraction Pipeline (Step 3)

Phase 2, Step 3 implements an end-to-end OCR and structured field extraction engine supporting digital PDFs, scanned/rasterized PDFs, and standalone images (PNG/JPEG) with field-level provenance and sensitive financial data masking.

### A. Multi-Format Text Recognition Engine (`app/extraction/ocr_engine.py`)
- **Digital PDF Extraction:** Directly extracts embedded text streams page-by-page via `pypdf`.
- **Scanned PDF Rendering & OCR:** For scanned or rasterized PDFs with insufficient digital text, renders pages to images via `pdf2image` (`pdftoppm`) at up to 2500px resolution and extracts text using local Tesseract OCR (`pytesseract`).
- **Image Recognition:** Directly processes PNG and JPEG files using local Tesseract OCR with automatic image normalization.
- **Bounded Resource Limits:** Enforces hard caps on pages (`MAX_PAGES_LIMIT = 10`), rendering resolution, per-page character lengths, and total document text to prevent resource exhaustion.

### B. Category-Specific Field Extraction (`app/extraction/parsers.py`)
Deterministic rules extract canonical key-value fields for each document category:
1. **`TAX_CERTIFICATE`:** `gstin`, `legal_entity_name`, `registration_date`, `registered_address`, `taxpayer_type`.
2. **`BANK_PROOF`:** `bank_name`, `account_holder_name`, `account_number`, `ifsc_code`, `routing_number`, `account_type`.
3. **`CERTIFICATE_OF_INCORPORATION`:** `company_name`, `cin_or_reg_number`, `incorporation_date`, `registered_jurisdiction`.
4. **`ADDRESS_PROOF`:** `resident_or_entity_name`, `full_address`, `issue_date`, `document_type`.
5. **`OTHER`:** Dynamic fallback extracting detected key-value identifiers.

### C. Field-Level Provenance & Sensitive Data Protection
- **Field Provenance:** Every extracted field records its source:
  - `page_number`: Original 1-indexed page where field was located.
  - `extraction_method`: `DIGITAL_TEXT` vs `OCR`.
  - `evidence_location`: Exact location (e.g. `Page 1, Line 3`).
  - `evidence_snippet`: Verbatim quotation snippet of the source document text.
- **PII & Financial Protection:** Sensitive account numbers are masked by default (`masked_value = "**********7890"`), preventing exposure in UI drawers, API responses, and activity logs.
- **Missing Field Determinism (Zero Hallucination):** If an expected field is absent (e.g. registration date or address omitted), the engine marks the field as `MISSING` (`value=None`) with reason `"Field not detected in document content."`. It never invents placeholder values.
- **Lifecycle Cascade:** Extractions are linked via `ON DELETE CASCADE` to `vendor_documents`. Deleting a document physically removes the file and cascades extraction record cleanup.

### D. REST API Endpoints
- `POST /api/v1/vendors/{vendor_id}/documents/{document_id}/extract`: Triggers OCR/extraction and persists result.
- `GET /api/v1/vendors/{vendor_id}/documents/{document_id}/extraction`: Returns latest extraction and field provenance.
- `GET /api/v1/vendors/{vendor_id}/documents/{document_id}/extraction-history`: Returns extraction audit history.
- `GET /api/v1/vendors/{vendor_id}/extractions`: Returns extractions across all vendor documents.

---

## 6. Extraction Confidence, Normalization & Evidence Inspection (Step 4)

Phase 2, Step 4 strengthens the extraction foundation by providing explainable, signal-grounded confidence scores, a dedicated normalization layer, honest provenance integrity, and interactive original document page inspection.

### A. Explainable Quality Assessment (`app/extraction/confidence.py`)
- **Measured Signals (Zero Hardcoded Constants):** Field confidence is calculated from six concrete, verifiable signals:
  1. `source_quality`: Base clarity of the underlying text recognition (`1.0` for digital PDF, `0.85` for OCR).
  2. `label_match`: Exactness of the detected identifier header or keyword label (`0.70` - `1.0`).
  3. `format_validity`: Conformance of the extracted value to statutory regex or structural rules (`1.0` valid, `0.20` malformed).
  4. `normalization_adjustment`: Penalty applied if value required OCR error correction (e.g. `O` $\leftrightarrow$ `0`) or trimming.
  5. `ambiguity_penalty`: Deductions if multiple competing candidates were found or date formats are ambiguous (`0.30` - `0.45` penalty).
  6. `provenance_quality`: Completeness of document coordinates, page numbers, and verbatim evidence snippets (`1.0`).
- **Composite Quality Score:** Weighted formula:
  $$\text{Composite} = (0.20 \times \text{source}) + (0.25 \times \text{label}) + (0.30 \times \text{format}) + (0.15 \times \text{provenance}) + (0.10 \times \text{norm}) - \text{penalty}$$
- **Presentation Disclaimer:** Explicitly documented as **"Extraction Quality Score"** or **"Evidence Quality"** measuring signal alignment and format validity—**never** labeled as a statistical probability of document authenticity or external legal validity.
- **Explainable Thresholds:**
  - $\ge 0.75$: `EXTRACTED` (High confidence).
  - $< 0.75$: `NEEDS_REVIEW` (Human review recommended with documented rationale).

### B. Distinct 4-State Field Status Model
1. **`EXTRACTED`:** Field located with high confidence ($\ge 0.75$), passing statutory format checks with clear evidence snippet.
2. **`NEEDS_REVIEW`:** Field detected but confidence $< 0.75$, format validation failed, OCR character repair was applied, or date format is ambiguous.
3. **`MISSING`:** Field was not detected in document content (`value=None`, `source=None`, `page_number=None`).
4. **`UNREADABLE`:** Region detected with relevant labels, but content was garbled or below OCR confidence threshold (`limitation_or_reason="IMAGE_RESOLUTION_LOW"` or `"OCR_TEXT_GARBLED"`). Retains page number and region for human triage.

### C. Canonical Normalization Layer (`app/extraction/normalization.py`)
- **GSTIN Normalization (`normalize_gstin`):** Enforces 15-character statutory format. Tracks OCR character repairs (`O` $\leftrightarrow$ `0`, `I` $\leftrightarrow$ `1`), notes changes, and applies a confidence penalty.
- **Date Normalization (`normalize_date`):** Standardizes valid dates into ISO 8601 (`YYYY-MM-DD`). Detects ambiguous slash dates (e.g. `03/04/2024` where day/month cannot be resolved without guessing) and sets `NEEDS_REVIEW` without fabricating assumptions.
- **Legal Entity Names (`normalize_entity_name`):** Cleans excess whitespace while strictly preserving statutory corporate suffixes (`Pvt Ltd`, `LLC`, `Corp`, `Inc`) without aggressive title-casing.
- **Addresses (`normalize_address`):** Reconnects hyphenated line breaks (`Indus-\ntrial` $\to$ `Industrial`) and standardizes spacing.
- **Bank Identifiers (`normalize_ifsc`, `normalize_account_number`):** Normalizes 11-char IFSC codes and masks account numbers (`****1234`) with zero raw PII leaks.

### D. Original Page Preview & Evidence Inspection Modal
- **Dynamic On-Demand Page Rendering (`GET /pages/{page}/preview`):** Renders the requested document page in memory via `pdf2image` (`pdftoppm`) as a PNG stream with `Cache-Control: private, no-store`. Zero permanent disk plaintext.
- **Access Control:** Validates document and vendor relationship; cross-vendor access is rejected with `HTTP 404`.
- **Interactive UI Modal:**
  - High-resolution document canvas with multi-page navigation controls.
  - Evidence inspection side panel showing normalized value, status badge, quality percentage, signal breakdown, and verbatim evidence quote.
  - **Evidence-Only Non-Mutation Principle:** Disclaims that extraction is structured evidence gathering only and never mutates vendor data or alters approval decisions.

---

## 10. Health & Readiness Probes

- **`GET /healthz` (Liveness):** Process check (`200 OK`, `{"status": "alive"}`).
- **`GET /readyz` (Readiness):** Dependency probe (`200 OK` with database connected; `503 Service Unavailable` if degraded).

---

## 11. Verification & Test Execution

### Backend Automated Test Suite
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/ -v
```
**Result:** **195 passed in 71.81s** (Exit code: `0`).

Includes complete coverage across:
- `test_extraction_quality.py`: 20 new tests covering normalization (GSTIN, dates, names, addresses, IFSC, account masking), date ambiguity detection without guessing, OCR character repair penalties, unreadable field classification, signal breakdown calculation, explainable thresholds, deterministic reproducibility, and authenticated page preview API streaming.
- `test_extraction.py`: 7 comprehensive extraction tests (digital PDF extraction, scanned PDF OCR rendering, image OCR recognition, missing field determinism, field-level provenance tracking, account number masking, cascade deletion, and vendor decision preservation).
- `test_classification.py`: 17 comprehensive classification tests (digital PDF text extraction, empty/scanned PDF handling, image file rejection without OCR, incorporation/tax/bank/address rule scoring, ambiguous and conflicting signals, filename-only bounds, classify/get/history endpoints, cross-vendor isolation, and proof that vendor compliance status is unmutated).
- `test_documents.py`: 30 tests covering intake validation, bounded chunked streaming, 10MB exact boundary and 1-byte overflow checks, path traversal and symlink rejection, sanitized error messages, two-phase staged deletion failure handling, database rollback recovery, and idempotent missing file deletion.
- `test_end_to_end_lifecycle.py`: 5 comprehensive lifecycle tests (Submission $\to$ Persistence $\to$ Validation $\to$ Decision $\to$ Status Update $\to$ History $\to$ Correction $\to$ Re-evaluation).
- `test_decision_api.py`: 13 integration tests for decision routes, transactional integrity, and explainability.
- `test_decision_engine.py`: 31 tests covering policy mapping, registry coverage, and action thresholds.
- `test_validation_rules.py`: 18 tests for country-specific statutory formats and consistency.
- `test_validation_engine.py`: 6 tests for engine orchestration and finding aggregation.
- `test_validation_api.py`: 5 tests for validation endpoints.
- `test_security_and_reliability.py`: 15 tests for Fernet encryption, key rotation, and migration.
- `test_vendors.py`: 10 tests for intake validation, persistence, and account masking.
- `test_health.py` & `test_config.py`: 12 tests for operational health probes and environment config.

### Frontend Development & Build
```bash
npm --prefix frontend run build
```
**Result:** TypeScript validation passes cleanly (0 errors), esbuild bundles in ~140ms.

---

## 12. Scope Boundaries & Deferred Capabilities (Beyond Phase 2, Step 4)

In strict adherence to Phase 2, Step 4 boundaries, the following advanced capabilities are deliberately deferred to subsequent roadmap steps:
- **Cross-Document Consistency Validation:** Automated reconciliation between document-extracted fields and vendor form fields (e.g. matching legal entity name on tax certificate vs bank statement vs web form) (Planned: Phase 2, Step 5).
- **Discrepancy Detection & Highlighting:** Generating cross-document discrepancy flags and confidence scores for human reviewer triage (Planned: Phase 2, Step 5).
- **Automated Document-Driven Compliance Decisioning:** Directly altering vendor approval status based on document contents (Planned: Phase 2, Step 5).
- **External Authority Registries:** Independent real-time lookups against GSTIN, IRS, or MCA portals (Planned: Phase 3).
- **Human-in-the-Loop Review Queues:** Dedicated exception triage and manual document approval workflows (Planned: Phase 3).
