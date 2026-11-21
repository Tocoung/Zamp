# Zamp — AI-Powered Vendor Onboarding Automation

> **Case Study:** Zamp AI Solutions Analyst Case Study  
> **Phase:** 1 (Step 2 — Vendor Data Model & Submission Interface)  
> **Status:** Vendor Intake & Directory Implemented & Verified

An automated platform designed to streamline vendor company onboarding, compliance document extraction, multi-source verification, decisioning (Approved / Pending / Rejected), and human-in-the-loop review.

---

## 1. Architecture & Technology Stack

The project uses a clean **Modular Monolith** architecture with decoupled presentation and backend layers:

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + Lucide React
- **Backend:** Python 3.9+ + FastAPI + Pydantic v2 + Uvicorn
- **Persistence:** SQLAlchemy 2.0 (Active: SQLite with deterministic path resolution; Production interface: PostgreSQL via `DATABASE_URL` with driver)
- **Testing:** Pytest + FastAPI TestClient (HTTPX) with temporary isolated SQLite databases

Detailed architectural boundaries and module roadmaps can be found in [docs/architecture.md](docs/architecture.md).

---

## 2. Implemented Features (Step 2)

### A. Vendor Data Model & Persistence
Structured SQLAlchemy ORM entity (`Vendor`) mapped to table `vendors`:
- **Identity & Company Info:** UUID primary key, legal entity name, trade name / DBA (optional), business type, country of incorporation, company registration number.
- **Contact Details:** Contact person full name, business email, contact phone number.
- **Registered Address:** Address lines 1 & 2, city, state/province, postal code, country.
- **Tax Details:** Tax identification type (EIN, VAT, GSTIN, PAN, CRN), tax identification number.
- **Banking Information:** Account holder name, bank name, bank account number (secured/encrypted storage), routing number (ABA/SWIFT/IFSC), bank country.
- **System Metadata:** Initial onboarding status `SUBMITTED`, UTC submission timestamp (`created_at`), and `updated_at`.

### B. Backend REST API
Exposed under prefix `/api/v1/vendors`:
1. `POST /api/v1/vendors`: Accepts vendor registration payload, performs strict Pydantic v2 structural validation and sanitization, generates UUID and `SUBMITTED` status, persists to database, and returns `201 Created` with masked banking information.
2. `GET /api/v1/vendors`: Returns paginated summary records (`total`, `page`, `page_size`, `total_pages`). Omits sensitive banking details from listing responses.
3. `GET /api/v1/vendors/{vendor_id}`: Returns complete record for a given UUID with bank account number masked (`••••••••1234`). Returns structured `404 Not Found` if the vendor does not exist.

### C. Data Security & Masking
- Raw bank account numbers are stored in the database for financial settlement, but are **strictly masked** in all API responses (`••••••••9012`).
- Raw account numbers are **never printed to logs, console output, or client-side listings**.

### D. Frontend User Interface
- **Registration Form:** 5-section intake form with client-side required field and email format validation, loading spinners, error alerts, and success banners displaying the newly generated Vendor UUID.
- **Vendor Directory:** Paginated table listing submitted vendors with status badges (`SUBMITTED`), search filtering, and an "Inspect" modal displaying complete entity records.
- **System Health:** Tabbed navigation preserving live backend operational probes and architecture roadmap.

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

4. **Configure environment:**
   ```bash
   cp .env.example .env
   ```

5. **Run backend automated tests (executes in isolated temporary database):**
   ```bash
   pytest
   ```

6. **Start the FastAPI development server:**
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
