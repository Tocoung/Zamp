"""Service Layer Architecture.

This package encapsulates domain and business logic, strictly separated from
the HTTP presentation layer (FastAPI routers) and raw persistence mechanisms.

Planned modules across project phases:
- vendor_service.py: Vendor profile intake and lifecycle state management (Phase 1)
- document_service.py: Document storage, extraction orchestration, and OCR (Phase 2)
- validation_service.py: Rule-based cross-checks, VAT/Tax format & banking checks (Phase 2)
- decision_service.py: Heuristic and LLM-assisted evaluation engine (Phase 3)
- review_service.py: Human-in-the-loop exception review and approvals (Phase 3)
- communication_service.py: Vendor notification and missing document requests (Phase 3)
- audit_service.py: Immutable audit logging and event tracking (Phase 4)
"""
