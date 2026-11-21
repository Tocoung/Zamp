# Zamp — AI-Powered Vendor Onboarding Automation

> **Case Study:** Zamp AI Solutions Analyst Case Study  
> **Phase:** 1 (Step 3 — Deterministic Validation Engine)  
> **Status:** Fully Implemented, Unit-Tested, and Verified  

An automated platform designed to streamline vendor company onboarding, compliance document extraction, multi-source verification, deterministic validation, decisioning (Approved / Pending / Rejected), and human-in-the-loop review.

---

## 1. Architecture & Technology Stack

The project uses a clean **Modular Monolith** architecture with decoupled presentation and backend layers:

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + Lucide React
- **Backend:** Python 3.9+ + FastAPI + Pydantic v2 + Uvicorn + Cryptography (Fernet)
- **Validation Engine:** Modular, decoupled rule engine (`backend/app/validation/`) evaluating required fields, country-aware formats, and cross-field consistency.
- **Persistence:** SQLAlchemy 2.0 (Active: SQLite with deterministic path resolution; Production interface: PostgreSQL via `DATABASE_URL` with driver)
- **Testing:** Pytest + FastAPI TestClient (HTTPX) with temporary isolated SQLite databases (66 automated tests)

Detailed architectural boundaries and module roadmaps can be found in [docs/architecture.md](docs/architecture.md).

---

## 2. Deterministic Validation Engine (Step 3)

The validation engine resides in `backend/app/validation/` and provides a reusable, deterministic rules evaluation framework.

### A. Core Architecture & Decoupling
- **`engine.py`:** Orchestrates evaluation across active rules, calculates summary metrics, ensures deterministic sorting, and builds the `ValidationResult`.
- **`models.py`:** Declares structured findings (`ValidationFinding`), summary counts (`ValidationSummary`), and evaluation results (`ValidationResult`).
- **`rules/base.py`:** Reusable `ValidationRule` abstract base class defining rule metadata, severity, target fields, and the `validate()` interface.
- **`rules/required.py`:** Mandatory-field checks across all 19 required vendor attributes.
- **`rules/formats.py`:** Country-aware syntax and format rules for contact info, tax identifiers, and banking routing codes.
- **`rules/consistency.py`:** Cross-field sanity and compatibility rules.
- **`registry.py`:** Rule registry managing rule registration and deterministic ordering.
- **`config.py`:** Runtime configuration supporting rule enabling/disabling, ruleset versioning (`1.0.0`), and severity overrides.

### B. Severity Semantics & Outcome Mapping
Each finding carries a severity:
- `ERROR`: Violation of mandatory syntax, checksum, or required fields. Prevents the submission from being valid.
- `WARNING`: Discrepancy or unusual pattern (e.g. account holder name mismatch, cross-border routing) that warrants review, but does not strictly invalidate data syntax.
- `INFO`: Informational notes on multinational operations or unsupported tax regimes.

**Outcome Status Mapping:**
- `PASSED`: Zero `ERROR` findings and zero `WARNING` findings (`valid: true`).
- `PASSED_WITH_WARNINGS`: Zero `ERROR` findings, at least one `WARNING` finding (`valid: true`).
- `FAILED`: One or more `ERROR` findings (`valid: false`).

### C. Supported Jurisdictions & Initial Ruleset
1. **Required Fields:** All 19 required fields in `VendorCreate` are validated. Empty strings and whitespace-only values fail. Optional fields (`trade_name`, `address_line2`) never fail.
2. **Contact Formats:**
   - Email: RFC 5322 syntax (`FMT_EMAIL_STRUCTURE`).
   - Phone: International structural check (7–17 digits with optional `+` and separators; reachability is not queried).
3. **Tax Identifiers:**
   - India GSTIN: 15-character statutory format (`^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$`).
   - India PAN: 10-character statutory format (`^[A-Z]{5}[0-9]{4}[A-Z]{1}$`).
   - US EIN: 9 numeric digits (`^[0-9]{2}-?[0-9]{7}$`) with validation against unassigned IRS campus prefixes.
   - UK VAT: 9 or 12 numeric digits with optional `GB` prefix (`^(?:GB)?\s*([0-9]{9}|[0-9]{12})$`).
   - *Unsupported Tax Regimes:* Emits an `INFO` note (`TAX_FORMAT_UNSUPPORTED_NOTE`) without inventing arbitrary validation rules.
4. **Banking Routing Identifiers:**
   - India IFSC: 11 characters starting with 4 letters, `0`, and 6 alphanumeric characters (`^[A-Z]{4}0[A-Z0-9]{6}$`).
   - US ABA Routing: 9 numeric digits verified against Federal Reserve Mod-10 checksum:
     $$[3(d_1 + d_4 + d_7) + 7(d_2 + d_5 + d_8) + 1(d_3 + d_6 + d_9)] \pmod{10} = 0$$
   - SWIFT / BIC: 8 or 11 characters (`^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$`).
5. **Bank Account Number Structural Checks:**
   - Length between 6 and 34 characters (domestic accounts and IBAN).
   - Rejection of dummy repeating sequences (`00000000`) and simple runs (`12345678`).
   - **Zero sensitive data exposure:** The raw account number is never logged or included in finding messages.
6. **Cross-Field Consistency:**
   - Tax Type vs. Country: Flags GSTIN/PAN outside India or EIN outside US as `WARNING`.
   - Routing Code vs. Bank Country: Flags IFSC outside India or ABA outside US as `WARNING`.
   - Cross-Border Operations: Emits `INFO` note when incorporation country differs from registered address.
   - Account Holder Name Matching: Compares token overlap against legal and trade names; mismatch emits `WARNING`.

### D. Adding a New Validation Rule
1. Subclass `ValidationRule` in `backend/app/validation/rules/`.
2. Implement `validate(self, data, context, config) -> List[ValidationFinding]`.
3. Register the rule in `backend/app/validation/registry.py` under `create_default_registry()`.

### E. Validation API Endpoints
- `POST /api/v1/vendors/validate`: Evaluates an unsaved vendor payload (complete or partial) without database writes.
- `POST /api/v1/vendors/{vendor_id}/validate`: Loads an existing stored vendor, decrypts the account number internally solely for structural length checks, and evaluates the record without modifying vendor status.

---

## 3. Security & Reliability Architecture (Step 2.1)

- **Encryption at Rest:** Bank account numbers are stored as Fernet authenticated ciphertext (`enc:v1:<token>`).
- **Fail-Safe Startup:** If `VENDOR_DATA_ENCRYPTION_KEY` is missing or invalid, application startup aborts immediately with a `RuntimeError`.
- **Transaction Rollback:** `VendorService.create_vendor()` executes explicit `db.rollback()` on persistence errors.
- **Deterministic Pagination:** Composite sorting `created_at DESC, id ASC` prevents tie-breaking inconsistencies.
- **Submission Locking:** Form submit locks immediately after submission (`Submitted (Edit to Re-submit)`), unlocking on field edit.

---

## 4. Operational Health Probes

1. **`GET /healthz` (Liveness Probe):** Confirms application process is running (`200 OK`, `{"status": "alive"}`). Does not touch database.
2. **`GET /readyz` (Readiness Probe):** Verifies downstream database connectivity (`200 OK` when healthy; `503 Service Unavailable` when degraded).
3. **`GET /api/v1/health` (Frontend Diagnostic):** Returns diagnostic status, database state, environment, and version.

---

## 5. Development Setup & Testing

### Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Run automated tests (66 tests in isolated temporary database)
pytest tests -v
# Start API server
uvicorn app.main:app --port 8000 --reload
```

### Frontend
```bash
cd frontend
npm ci
npm run build
npm run dev
```

---

## 6. Implementation Roadmap

1. **Phase 1: Foundation & Core Onboarding Engine**
   - Step 1: Project Foundation & Architecture *(Completed)*
   - Step 1.1: Foundation Hardening & Architecture Alignment *(Completed)*
   - Step 2: Vendor Data Model & Submission API *(Completed)*
   - Step 2.1: Vendor Data Security & Reliability Hardening *(Completed)*
   - Step 3: Deterministic Validation Engine *(Completed)*
   - Step 4: Decision Engine *(Next)*
   - Step 5: End-to-End Integration *(Planned)*
2. **Phase 2: Intelligent Document Processing & Cross-Document Verification**
3. **Phase 3: Exception Handling & Human-in-the-Loop Review**
4. **Phase 4: Product Dashboard & Audit Trail**
5. **Phase 5: Advanced Intelligence & Production Polish**
