"""Synthetic demonstration data seeding script for Zamp Vendor Onboarding Automation.

Provides reproducible, clearly fictional, synthetic vendor submissions covering:
1. Clean submission -> APPROVED
2. Incomplete submission (missing required registration number & phone) -> PENDING
3. Review-required consistency discrepancy (bank account holder name mismatch) -> PENDING
4. Explicitly blocking malformed format (invalid statutory GSTIN format) -> REJECTED

Usage:
    python backend/app/scripts/seed_demo_data.py
    python backend/app/scripts/seed_demo_data.py --reset
    python backend/app/scripts/seed_demo_data.py --no-decisions
"""

import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any

# Ensure backend root directory is on python path for direct CLI execution
backend_path = Path(__file__).resolve().parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine
from app.db.base import Base
from app.models.vendor import Vendor
from app.models.decision import VendorDecision
from app.models.activity import VendorActivity
from app.core.security import encrypt_account_number
from app.services.decision_service import decision_service
from app.core.logging import logger

DEMO_LABEL_TAG = "[DEMO]"

# 4 explicitly synthetic, fictional vendor datasets
DEMO_VENDORS_PAYLOADS: List[Dict[str, Any]] = [
    {
        "expected_outcome": "APPROVED",
        "description": "Clean, complete Indian vendor submission with matching legal and banking identities.",
        "data": {
            "legal_name": "Solaris Tech Labs Private Limited [DEMO]",
            "trade_name": "Solaris Demo",
            "business_type": "Private Limited",
            "country_of_incorporation": "India",
            "registration_number": "U72200KA2023PTC999001",
            "contact_name": "Aarav Sharma",
            "contact_email": "aarav.sharma@solaris-demo.example.com",
            "contact_phone": "+919876543210",
            "address_line1": "101 Innovation Park, Koramangala",
            "address_line2": "Tower B, 4th Floor",
            "city": "Bengaluru",
            "state_province": "Karnataka",
            "postal_code": "560034",
            "address_country": "India",
            "tax_id_type": "GSTIN",
            "tax_id_number": "29AAACS1234D1Z5",
            "bank_account_holder_name": "Solaris Tech Labs Private Limited [DEMO]",
            "bank_name": "HDFC Bank",
            "bank_account_number": "9999000112233",
            "bank_routing_number": "HDFC0000123",
            "bank_country": "India",
            "status": "SUBMITTED",
        },
    },
    {
        "expected_outcome": "PENDING",
        "description": "Incomplete submission missing statutory registration number and phone number.",
        "data": {
            "legal_name": "Nova Retail Ventures LLP [DEMO]",
            "trade_name": "Nova Retail Demo",
            "business_type": "Partnership",
            "country_of_incorporation": "India",
            "registration_number": "",  # Missing mandatory registration number
            "contact_name": "Priya Patel",
            "contact_email": "priya.patel@novaretail-demo.example.com",
            "contact_phone": "",  # Missing mandatory phone
            "address_line1": "42 Commercial Street",
            "address_line2": None,
            "city": "Mumbai",
            "state_province": "Maharashtra",
            "postal_code": "400001",
            "address_country": "India",
            "tax_id_type": "GSTIN",
            "tax_id_number": "27AAAPN5678E1Z9",
            "bank_account_holder_name": "Nova Retail Ventures LLP [DEMO]",
            "bank_name": "ICICI Bank",
            "bank_account_number": "8888000223344",
            "bank_routing_number": "ICIC0000456",
            "bank_country": "India",
            "status": "SUBMITTED",
        },
    },
    {
        "expected_outcome": "PENDING",
        "description": "Review-required consistency warning: bank account holder name differs from company legal name.",
        "data": {
            "legal_name": "Zenith Global Logistics Corp [DEMO]",
            "trade_name": "Zenith Logistics Demo",
            "business_type": "Private Limited",
            "country_of_incorporation": "India",
            "registration_number": "U63090DL2022PTC888002",
            "contact_name": "Rohan Verma",
            "contact_email": "rohan.verma@zenith-demo.example.com",
            "contact_phone": "+919123456789",
            "address_line1": "88 Okhla Industrial Area, Phase III",
            "address_line2": None,
            "city": "New Delhi",
            "state_province": "Delhi",
            "postal_code": "110020",
            "address_country": "India",
            "tax_id_type": "GSTIN",
            "tax_id_number": "07AAACZ9012F1Z3",
            "bank_account_holder_name": "Apex Holdings International Ltd",  # Discrepancy with legal name
            "bank_name": "Axis Bank",
            "bank_account_number": "7777000334455",
            "bank_routing_number": "UTIB0000789",
            "bank_country": "India",
            "status": "SUBMITTED",
        },
    },
    {
        "expected_outcome": "REJECTED",
        "description": "Explicit blocking violation: malformed statutory tax identifier (invalid GSTIN syntax).",
        "data": {
            "legal_name": "Vortex Industrial Supplies Inc [DEMO]",
            "trade_name": "Vortex Supplies Demo",
            "business_type": "Private Limited",
            "country_of_incorporation": "India",
            "registration_number": "U28110TN2021PTC777003",
            "contact_name": "Kavita Sundaram",
            "contact_email": "kavita.s@vortex-demo.example.com",
            "contact_phone": "+919988776655",
            "address_line1": "15 Guindy Industrial Estate",
            "address_line2": None,
            "city": "Chennai",
            "state_province": "Tamil Nadu",
            "postal_code": "600032",
            "address_country": "India",
            "tax_id_type": "GSTIN",
            "tax_id_number": "33INVALID_SYNTAX_999",  # Explicitly malformed GSTIN
            "bank_account_holder_name": "Vortex Industrial Supplies Inc [DEMO]",
            "bank_name": "State Bank of India",
            "bank_account_number": "6666000445566",
            "bank_routing_number": "SBIN0000999",
            "bank_country": "India",
            "status": "SUBMITTED",
        },
    },
]


def reset_demo_data(session: Session) -> int:
    """Safely deletes only records with [DEMO] in legal_name or trade_name without touching real records."""
    demo_vendors = list(
        session.scalars(
            select(Vendor).where(
                Vendor.legal_name.contains(DEMO_LABEL_TAG) | Vendor.trade_name.contains("Demo")
            )
        ).all()
    )
    count = len(demo_vendors)
    for v in demo_vendors:
        session.delete(v)
    session.commit()
    logger.info(f"Reset {count} synthetic demonstration vendor record(s).")
    return count


def seed_demo_vendors(session: Session, run_decisions: bool = True) -> List[Dict[str, Any]]:
    """Idempotently seeds the 4 synthetic vendor scenarios and optionally computes their decisions."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    results = []

    for item in DEMO_VENDORS_PAYLOADS:
        payload = dict(item["data"])
        legal_name = payload["legal_name"]

        # Check if already exists (idempotency check by legal_name)
        existing = session.scalar(select(Vendor).where(Vendor.legal_name == legal_name))
        if existing:
            vendor = existing
            created_new = False
        else:
            # Encrypt raw account number at rest
            raw_acc = payload.pop("bank_account_number", "000000000000")
            enc_acc = encrypt_account_number(raw_acc)
            payload["bank_account_number"] = enc_acc

            vendor = Vendor(**payload)
            session.add(vendor)
            session.flush()

            # Record initial submission activity
            initial_act = VendorActivity(
                vendor_id=vendor.id,
                event_type="VENDOR_SUBMITTED",
                title="Vendor Registration Submitted",
                description="Initial vendor registration submitted with status SUBMITTED.",
                status="SUBMITTED",
                created_at=vendor.created_at,
            )
            session.add(initial_act)
            session.commit()
            session.refresh(vendor)
            created_new = True

        actual_status = vendor.status

        # Evaluate decision if requested and currently SUBMITTED
        if run_decisions and vendor.status == "SUBMITTED":
            try:
                dec_result = decision_service.run_decision_for_vendor(db=session, vendor_id=vendor.id)
                actual_status = dec_result.status.value
            except Exception as e:
                actual_status = f"EVAL_FAILED: {type(e).__name__}"

        results.append({
            "id": vendor.id,
            "legal_name": vendor.legal_name,
            "created_new": created_new,
            "expected_outcome": item["expected_outcome"],
            "actual_status": actual_status,
            "description": item["description"],
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="Zamp Synthetic Demo Data Seeder")
    parser.add_argument("--reset", action="store_true", help="Remove all [DEMO] vendors and exit")
    parser.add_argument("--no-decisions", action="store_true", help="Leave demo vendors in SUBMITTED status without evaluating decisions")
    args = parser.parse_args()

    with SessionLocal() as session:
        if args.reset:
            count = reset_demo_data(session)
            print(f"Successfully removed {count} demo vendor records.")
            return

        run_decisions = not args.no_decisions
        seeded = seed_demo_vendors(session, run_decisions=run_decisions)

        print("\n========================================================")
        print(" Zamp Synthetic Demonstration Data Seed Complete")
        print("========================================================")
        for s in seeded:
            action = "Created" if s["created_new"] else "Already Exists"
            match_icon = "[OK]" if s["actual_status"] == s["expected_outcome"] else "[MISMATCH]"
            print(f"\n{match_icon} {s['legal_name']}")
            print(f"    ID:       {s['id']}")
            print(f"    Action:   {action}")
            print(f"    Expected: {s['expected_outcome']} | Actual: {s['actual_status']}")
            print(f"    Scenario: {s['description']}")
        print("\n========================================================\n")


if __name__ == "__main__":
    main()
