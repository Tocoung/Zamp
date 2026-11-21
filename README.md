# Zamp — AI-Powered Vendor Onboarding Automation

> **Case Study:** Zamp AI Solutions Analyst Case Study  
> **Phase:** 1 (Step 4.1 — Decision Policy & Evidence Hardening)  
> **Status:** Fully Hardened, Unit-Tested, and Verified (110 Automated Tests Passing)  

An automated platform designed to streamline vendor company onboarding, compliance document extraction, multi-source verification, deterministic validation, explainable decisioning (`APPROVED` / `PENDING` / `REJECTED`), and human-in-the-loop review.

---

## 1. Architecture & Technology Stack

The project uses a clean **Modular Monolith** architecture with decoupled presentation, validation, decision, and service layers:

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + Lucide React
- **Backend:** Python 3.9+ + FastAPI + Pydantic v2 + Uvicorn + Cryptography (Fernet)
- **Validation Engine:** Modular, decoupled rule engine (`backend/app/validation/`) evaluating 28 deterministic rules across required fields, country-aware statutory formats, and cross-field consistency.
- **Decision Engine:** Deterministic business policy and explainability engine (`backend/app/decision/`) assigning `APPROVED`, `PENDING`, or `REJECTED` outcomes with stable reason codes and actionable recommendations.
- **Persistence:** SQLAlchemy 2.0 (Active: SQLite with deterministic path resolution; Production interface: PostgreSQL via `DATABASE_URL` with driver).
- **Audit History:** Dedicated `vendor_decisions` table preserving historical decision snapshots transactionally without duplicating sensitive banking data.
- **Testing:** Pytest + FastAPI TestClient with temporary isolated SQLite databases (**110 automated tests passing**).

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

## 3. Sample Decision Outputs

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

## 4. Deterministic Validation Engine (Step 3 Recap)

The underlying validation engine resides in `backend/app/validation/`:
- **Ruleset Version:** `1.0.0`
- **28 Active Deterministic Rules:** Mandatory fields, contact formats, India GSTIN/PAN, US EIN with IRS prefix check, UK VAT, India IFSC, US ABA Mod-10 checksum, SWIFT/BIC, bank account length/dummy checks, and cross-field consistency.
- **Privacy:** Evaluates decrypted account numbers in memory without logging or returning raw values in responses.
- **Endpoints:**
  - `POST /api/v1/vendors/validate`: Evaluates unsaved payloads without DB writes.
  - `POST /api/v1/vendors/{vendor_id}/validate`: Evaluates stored vendors without status mutation.

---

## 5. Security & Reliability Architecture (Step 2.1 Recap)

- **Encryption at Rest:** Bank account numbers are encrypted using Fernet (`AES-128-CBC + HMAC-SHA256`).
- **Fail-Safe Startup:** If `VENDOR_DATA_ENCRYPTION_KEY` is missing or invalid, application startup aborts immediately.
- **Masking:** API responses and UI screens only display masked account numbers (`••••••••5678`).
- **Zero Sensitive Data in Decision History:** Raw account numbers are strictly excluded from `validation_snapshot` and decision explanations.

---

## 6. Health & Readiness Probes

- **`GET /healthz` (Liveness):** Process check (`200 OK`, `{"status": "alive"}`).
- **`GET /readyz` (Readiness):** Dependency probe (`200 OK` with database connected; `503 Service Unavailable` if degraded).

---

## 7. Verification & Test Execution

### Backend Automated Test Suite
```bash
backend/.venv/bin/pytest backend/tests -v
```
**Result:** **110 passed in 2.52s** (Exit code: `0`).

### Frontend Production Build
```bash
npm --prefix frontend run build
```
**Result:** Compiled successfully with Vite v5.4.21 (Exit code: `0`).
