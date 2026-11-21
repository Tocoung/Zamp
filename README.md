# Zamp — AI-Powered Vendor Onboarding Automation

> **Case Study:** Zamp AI Solutions Analyst Case Study  
> **Phase:** 1 (Step 2.1 — Vendor Data Security & Reliability Hardening)  
> **Status:** Hardened, Encrypted at Rest & Fully Verified

An automated platform designed to streamline vendor company onboarding, compliance document extraction, multi-source verification, decisioning (Approved / Pending / Rejected), and human-in-the-loop review.

---

## 1. Architecture & Technology Stack

The project uses a clean **Modular Monolith** architecture with decoupled presentation and backend layers:

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + Lucide React
- **Backend:** Python 3.9+ + FastAPI + Pydantic v2 + Uvicorn + Cryptography (Fernet)
- **Persistence:** SQLAlchemy 2.0 (Active: SQLite with deterministic path resolution; Production interface: PostgreSQL via `DATABASE_URL` with driver)
- **Testing:** Pytest + FastAPI TestClient (HTTPX) with temporary isolated SQLite databases (35 automated tests)

Detailed architectural boundaries and module roadmaps can be found in [docs/architecture.md](docs/architecture.md).

---

## 2. Hardened Features & Security Architecture (Step 2.1)

### A. Authenticated Data Encryption at Rest
- **Algorithm:** Authenticated symmetric encryption via Fernet (`cryptography` library), implementing AES-128-CBC with PKCS7 padding and HMAC-SHA256 authentication.
- **Storage Format:** Stored under the versioned prefix `enc:v1:<fernet_token>` in `vendors.bank_account_number`.
- **Key Management:** Read from the `VENDOR_DATA_ENCRYPTION_KEY` environment variable. Never hardcoded or committed to git.
- **Fail-Safe Behavior:** The encryption utility raises `EncryptionConfigurationError` if the key is missing or invalid. It **never** silently falls back to plaintext storage.
- **Corrupted Ciphertext Protection:** Corrupted or tampered ciphertext raises `DecryptionError` and is never silently treated as plaintext.
- **Controlled Legacy Migration:** Includes an idempotent migration utility (`backend/app/db/migrate_encryption.py`) that detects unencrypted legacy records, encrypts them in place, and preserves data without downtime or data loss.
- **MVP vs. Production Notice:** While Fernet authenticated encryption provides strong confidentiality and integrity for this local MVP/prototype, an enterprise production financial platform requires envelope encryption backed by a Hardware Security Module (HSM) or cloud KMS (AWS KMS, GCP Cloud KMS, HashiCorp Vault) with automated key rotation and PCI-DSS compliance.

### B. Startup Reliability & Schema Safeguards
- **Startup Guard:** If database connectivity or required schema initialization fails during `lifespan()`, application startup fails immediately with a `RuntimeError` rather than serving traffic in a degraded or uninitialized state.
- **Non-Destructive Initialization:** Relies on `CREATE TABLE IF NOT EXISTS`, preserving all existing vendor records and database contents across restarts.
- **Operational Probes:** Process liveness (`/healthz`) confirms runtime execution, while readiness (`/readyz`) continues monitoring downstream database health.

### C. Transaction Rollback & Data Integrity
- **Transactional Rollback:** In `VendorService.create_vendor()`, any database persistence or commit error triggers an immediate `db.rollback()`, ensuring database sessions are never left in a poisoned transaction state.
- **Safe Server Errors:** Database exceptions are converted into clean 500 HTTP errors. Raw SQL queries, database credentials, and vendor banking data are never exposed in logs or API responses.

### D. Deterministic Pagination
- **Composite Sort Key:** Vendor listing queries sort by `Vendor.created_at.desc(), Vendor.id.asc()`, guaranteeing strictly deterministic record ordering across pagination boundaries even when multiple submissions share identical timestamps.

### E. Frontend Form Flow & Security Accuracy
- **Duplicate Submission Lock:** Once a submission succeeds, the form locks the submit button (`Submitted (Edit to Re-submit)`) and shows a clear lock indicator banner until any field is edited or the form is reset.
- **Directory Refresh:** Successfully submitting a vendor and clicking "View in Directory →" automatically triggers a fresh reload of the vendor directory.
- **Accurate UI Security Messaging:** Corrected inspection modal security badges to clarify that while bank account numbers are authenticated-encrypted at rest and masked in UI views, routing numbers and tax IDs remain unencrypted as needed for tax lookup and clearing network routing.

---

## 2. Directory Structure

```text
.
├── .env.example              # Master root environment template
├── .gitignore                # Strict version control exclusions
├── README.md                 # Project setup and operational documentation
├── docs/
│   └── architecture.md       # Comprehensive architecture specification
├── backend/
│   ├── .env.example          # Backend-specific environment template
│   ├── requirements.txt      # Pinned Python dependencies
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI entrypoint, lifespan, /healthz & /readyz probes
│   │   ├── core/             # Configuration & logging
│   │   │   ├── config.py     # Pydantic BaseSettings, path resolution & URL sanitizer
│   │   │   └── logging.py    # Structured application logging
│   │   ├── db/               # Persistence abstraction
│   │   │   ├── base.py       # SQLAlchemy 2.0 DeclarativeBase
│   │   │   └── session.py    # Engine, SessionLocal, and safe connectivity checks
│   │   ├── api/              # API presentation layer
│   │   │   ├── router.py     # Router aggregation & extension mount points
│   │   │   └── v1/
│   │   │       └── endpoints/
│   │   │           └── health.py # /api/v1/health diagnostic endpoint
│   │   └── services/         # Decoupled business logic (placeholder for Step 2+)
│   └── tests/                # Automated pytest suite (isolated test database)
│       ├── conftest.py       # Isolated test engine and session fixtures
│       ├── test_config.py    # Settings, path resolution & sanitizer tests
│       └── test_health.py    # Probes, diagnostics, and isolation tests
└── frontend/
    ├── package.json          # Node dependencies & scripts
    ├── package-lock.json     # Deterministic lockfile
    ├── tsconfig.json         # Strict TypeScript configuration
    ├── tsconfig.node.json    # Node TypeScript configuration
    ├── vite.config.ts        # Vite build tool configuration & pre-bundling
    ├── tailwind.config.js    # Tailwind design tokens
    ├── .env.example          # Frontend environment template
    ├── index.html            # Single page application template & fallback skeleton
    └── src/
        ├── App.tsx           # Application shell & landing UI
        ├── main.tsx          # React DOM entry point
        ├── vite-env.d.ts     # Vite client type definitions
        ├── config/api.ts     # Centralized API client & health polling
        └── components/       # Branded UI components
            ├── Header.tsx
            ├── BackendStatus.tsx
            ├── ArchitectureRoadmap.tsx
            └── Footer.tsx
```

---

## 3. Getting Started & Local Setup

### Prerequisites
- **Python:** 3.9 or higher
- **Node.js:** v18 or higher (tested on v26)
- **Git**

---

### Backend Setup

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install reproducible dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment & encryption key:**
   ```bash
   cp .env.example .env
   # Generate a local authenticated Fernet encryption key:
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   # Paste the generated key into your .env file as VENDOR_DATA_ENCRYPTION_KEY=<key>
   ```

5. **Run legacy data migration (if upgrading existing unencrypted database):**
   ```bash
   PYTHONPATH=. python3 -m app.db.migrate_encryption
   ```

6. **Run backend automated tests (executes in isolated temporary database):**
   ```bash
   pytest
   ```

7. **Start the FastAPI development server:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   - API Root: [http://localhost:8000/](http://localhost:8000/)
   - Liveness Probe: [http://localhost:8000/healthz](http://localhost:8000/healthz)
   - Readiness Probe: [http://localhost:8000/readyz](http://localhost:8000/readyz)
   - Diagnostic Endpoint: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
   - Interactive Swagger API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install reproducible Node dependencies via lockfile:**
   ```bash
   npm ci
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env.local
   ```

4. **Verify TypeScript build:**
   ```bash
   npm run build
   ```

5. **Start the Vite development server:**
   ```bash
   npm run dev
   ```
   - Frontend UI: [http://localhost:5173/](http://localhost:5173/)

---

## 4. Operational Probes & Health Check Architecture

The service exposes two standard operational probes alongside a rich diagnostic endpoint:

1. **`GET /healthz` (Liveness Probe):**
   - Verifies the application process is running and accepting HTTP requests.
   - Does not touch the database.
   - Status code: `200 OK`
   - Response: `{"status": "alive"}`

2. **`GET /readyz` (Readiness Probe):**
   - Verifies critical downstream dependencies (database connection).
   - Status code: `200 OK` when healthy; `503 Service Unavailable` when degraded.
   - Healthy response: `{"status": "ready", "dependencies": {"database": "connected"}}`
   - Degraded response: `{"status": "not_ready", "dependencies": {"database": "disconnected"}}`

3. **`GET /api/v1/health` (Frontend Diagnostic Endpoint):**
   - Preserved for frontend UI status widgets, version tracking, and environment reporting.
   - Returns `200 OK` when ready; `503 Service Unavailable` when degraded.
   - Response:
     ```json
     {
       "status": "healthy",
       "timestamp": "2026-11-21T00:00:00Z",
       "environment": "development",
       "version": "0.1.0",
       "database": "connected"
     }
     ```

---

## 5. Database Configuration & Path Resolution

- **Predictable SQLite Path Resolution:** Relative paths such as `sqlite:///./vendor_onboarding.db` are resolved automatically against the project root directory, guaranteeing consistent file placement regardless of the active terminal working directory.
- **Credential Masking:** Connection strings logged during startup and error handling are sanitized via `hide_password=True` to prevent credential exposure.
- **Driver Clarity:** SQLite is the default installed driver. Connecting to PostgreSQL in production requires installing a compatible DBAPI driver package (`psycopg2-binary` or `asyncpg`).

---

## 6. Agreed Five-Phase Roadmap

1. **Phase 1: Foundation & Core Onboarding Engine**
   - Step 1: Project Foundation & Architecture *(Completed)*
   - Step 1.1: Foundation Hardening & Architecture Alignment *(Completed)*
   - Step 2: Vendor Data Model & Submission API *(Completed)*
   - Step 3: Deterministic Validation *(Next)*
   - Step 4: Decision Engine *(Planned)*
   - Step 5: End-to-End Integration *(Planned)*
2. **Phase 2: Intelligent Document Processing & Cross-Document Verification**
3. **Phase 3: Exception Handling & Human-in-the-Loop Review**
4. **Phase 4: Product Dashboard & Audit Trail**
5. **Phase 5: Advanced Intelligence & Production Polish**
