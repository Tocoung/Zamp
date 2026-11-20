# Zamp — AI-Powered Vendor Onboarding Automation

> **Case Study:** Zamp AI Solutions Analyst Case Study  
> **Phase:** 1 (Step 1 — Project Foundation & Architecture)  
> **Status:** Foundation Implemented & Verified

An automated platform designed to streamline vendor company onboarding, compliance document extraction, multi-source verification, decisioning (Approved / Pending / Rejected), and human-in-the-loop review.

---

## 1. Architecture & Technology Stack

The project uses a clean **Modular Monolith** architecture with decoupled presentation and backend layers:

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + Lucide React
- **Backend:** Python 3.9+ + FastAPI + Pydantic v2 + Uvicorn
- **Persistence:** SQLAlchemy 2.0 (SQLite for zero-friction local development, PostgreSQL ready via `DATABASE_URL`)
- **Testing:** Pytest + FastAPI TestClient (HTTPX)

Detailed architectural boundaries and module roadmaps can be found in [docs/architecture.md](docs/architecture.md).

---

## 2. Directory Structure

```text
.
├── .env.example              # Root environment template
├── .gitignore                # Version control exclusions
├── README.md                 # Project setup and documentation
├── docs/
│   └── architecture.md       # Comprehensive architecture document
├── backend/
│   ├── .env.example          # Backend environment template
│   ├── requirements.txt      # Python dependencies
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI entrypoint & middleware configuration
│   │   ├── core/             # Configuration & logging
│   │   │   ├── config.py     # Pydantic BaseSettings environment loader
│   │   │   └── logging.py    # Structured logging
│   │   ├── db/               # Persistence layer
│   │   │   ├── base.py       # SQLAlchemy 2.0 DeclarativeBase
│   │   │   └── session.py    # Engine, SessionLocal, and health checks
│   │   ├── api/              # API presentation layer
│   │   │   ├── router.py     # Router aggregation & extension points
│   │   │   └── v1/
│   │   │       └── endpoints/
│   │   │           └── health.py # /api/v1/health diagnostic endpoint
│   │   └── services/         # Decoupled business logic (placeholder for Step 2+)
│   └── tests/                # Automated pytest suite
│       ├── conftest.py
│       ├── test_config.py
│       └── test_health.py
└── frontend/
    ├── package.json          # Node dependencies & scripts
    ├── tsconfig.json         # TypeScript configuration
    ├── vite.config.ts        # Vite build tool configuration
    ├── tailwind.config.js    # Tailwind design tokens
    ├── .env.example          # Frontend environment template
    ├── index.html            # Single page application template
    └── src/
        ├── App.tsx           # Application shell & landing UI
        ├── main.tsx          # React DOM entry point
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

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   ```

5. **Run backend tests:**
   ```bash
   pytest
   ```

6. **Start the FastAPI development server:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   - API Root: [http://localhost:8000/](http://localhost:8000/)
   - Health Check: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
   - Interactive Swagger API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install Node packages:**
   ```bash
   npm install
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

## 4. Verification & Health Check Endpoints

- **`GET /api/v1/health`**: Returns JSON status of the service, environment, timestamp, and live database engine connectivity.
  ```json
  {
    "status": "healthy",
    "timestamp": "2026-11-21T00:00:00Z",
    "environment": "development",
    "version": "0.1.0",
    "database": "connected"
  }
  ```
- **`GET /healthz`**: Simple container liveness probe (`{"status": "ok"}`).

---

## 5. Incremental Phase Roadmap

- **Phase 1: Foundation & Core Engine** *(Step 1 Complete; Step 2: Vendor entity models & API)*
- **Phase 2: Intelligent Document Processing** *(Uploads, OCR, cross-validation)*
- **Phase 3: Exception Handling & HITL Review** *(Decision engine, human review console, notifications)*
- **Phase 4: Product UI, Dashboard & Audit Trail** *(Full vendor portal, operations dashboard, audit log)*
- **Phase 5: Advanced Intelligence & Production Polish** *(LLM verification agents, anomaly scoring, deployment)*
