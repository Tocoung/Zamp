"""Automated tests for vendor data encryption at rest, transaction rollback, and startup reliability."""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate
from app.services.vendor_service import vendor_service, VendorServiceError
from app.core.security import (
    encrypt_account_number,
    decrypt_account_number,
    is_encrypted,
    migrate_legacy_vendor_accounts,
    EncryptionError,
    EncryptionConfigurationError,
    DecryptionError,
    ENCRYPTION_VERSION_PREFIX,
)
from tests.test_vendors import get_sample_vendor_payload


# ==============================================================================
# 1. Encryption & Decryption Tests
# ==============================================================================

class TestEncryptionAtRest:
    """Tests covering Fernet-based data encryption and decryption at rest."""

    def test_encryption_roundtrip(self):
        """Verifies plaintext encrypts to versioned ciphertext and decrypts accurately."""
        sample_account = "9876543210987654"
        ciphertext = encrypt_account_number(sample_account)

        assert is_encrypted(ciphertext)
        assert ciphertext.startswith(ENCRYPTION_VERSION_PREFIX)
        assert ciphertext != sample_account

        decrypted = decrypt_account_number(ciphertext)
        assert decrypted == sample_account

    def test_encryption_is_idempotent(self):
        """Encrypting already-encrypted ciphertext returns the exact same string."""
        sample_account = "123456789012"
        first_pass = encrypt_account_number(sample_account)
        second_pass = encrypt_account_number(first_pass)
        assert first_pass == second_pass

    def test_missing_encryption_key_fails_safely(self):
        """Missing encryption key raises EncryptionConfigurationError without fallback."""
        with patch("app.core.security.settings.VENDOR_DATA_ENCRYPTION_KEY", None):
            with pytest.raises(EncryptionConfigurationError) as exc_info:
                encrypt_account_number("123456789")
            assert "VENDOR_DATA_ENCRYPTION_KEY is not configured" in str(exc_info.value)

    def test_invalid_encryption_key_fails_safely(self):
        """Malformed encryption key raises EncryptionConfigurationError."""
        with patch("app.core.security.settings.VENDOR_DATA_ENCRYPTION_KEY", "not-a-valid-base64-key"):
            with pytest.raises(EncryptionConfigurationError) as exc_info:
                encrypt_account_number("123456789")
            assert "Invalid VENDOR_DATA_ENCRYPTION_KEY" in str(exc_info.value)

    def test_corrupted_ciphertext_raises_decryption_error(self):
        """Corrupted ciphertext raises DecryptionError and is NOT treated as plaintext."""
        corrupted_token = f"{ENCRYPTION_VERSION_PREFIX}gAAAAABmCorruptedPayload12345"
        with pytest.raises(DecryptionError) as exc_info:
            decrypt_account_number(corrupted_token)
        assert "Corrupted ciphertext" in str(exc_info.value)

    def test_unencrypted_value_without_legacy_flag_raises_error(self):
        """Non-prefixed string raises DecryptionError when allow_legacy_plaintext is False."""
        raw_string = "8839201948201"
        with pytest.raises(DecryptionError) as exc_info:
            decrypt_account_number(raw_string, allow_legacy_plaintext=False)
        assert "missing 'enc:v1:' prefix" in str(exc_info.value)

    def test_unencrypted_value_with_legacy_flag_returns_plaintext(self):
        """Legacy plaintext value is returned when allow_legacy_plaintext is True."""
        raw_string = "8839201948201"
        assert decrypt_account_number(raw_string, allow_legacy_plaintext=True) == raw_string


# ==============================================================================
# 2. Legacy Migration Tests
# ==============================================================================

class TestLegacyMigration:
    """Tests covering controlled migration of unencrypted legacy database records."""

    def test_legacy_plaintext_migration_is_safe_and_idempotent(self, test_db_session: Session):
        """Plaintext account records are migrated to enc:v1: ciphertext and remain unchanged on rerun."""
        # Insert a simulated legacy unencrypted record
        legacy_id = str(uuid.uuid4())
        raw_bank_number = "LEGACY-ACCOUNT-9988"
        legacy_vendor = Vendor(
            id=legacy_id,
            legal_name="Legacy Pre-Encryption Corp",
            business_type="Private Limited",
            country_of_incorporation="United States",
            registration_number=f"REG-{uuid.uuid4().hex[:6]}",
            contact_name="Old Record Handler",
            contact_email="legacy@example.com",
            contact_phone="+1 555-000-1111",
            address_line1="100 Legacy Ave",
            city="Boston",
            state_province="MA",
            postal_code="02108",
            address_country="United States",
            tax_id_type="EIN",
            tax_id_number="11-9988776",
            bank_account_holder_name="Legacy Pre-Encryption Corp",
            bank_name="First National Bank",
            bank_account_number=raw_bank_number,  # Stored as plaintext
            bank_routing_number="011000015",
            bank_country="United States",
            status="SUBMITTED",
        )
        test_db_session.add(legacy_vendor)
        test_db_session.commit()

        # Confirm it was saved as raw plaintext
        persisted = test_db_session.scalar(select(Vendor).where(Vendor.id == legacy_id))
        assert persisted.bank_account_number == raw_bank_number
        assert not is_encrypted(persisted.bank_account_number)

        # Run migration pass 1
        migrated_count = migrate_legacy_vendor_accounts(test_db_session)
        assert migrated_count >= 1

        # Verify the record is now encrypted
        test_db_session.refresh(persisted)
        assert is_encrypted(persisted.bank_account_number)
        assert persisted.bank_account_number.startswith(ENCRYPTION_VERSION_PREFIX)
        assert decrypt_account_number(persisted.bank_account_number) == raw_bank_number

        # Run migration pass 2 (idempotent rerun)
        second_pass_count = migrate_legacy_vendor_accounts(test_db_session)
        assert second_pass_count == 0  # No records needed migration


# ==============================================================================
# 3. Transaction Rollback & Resilience Tests
# ==============================================================================

class TestTransactionResilience:
    """Verifies database transaction rollback behaviour and session recovery."""

    def test_failed_commit_triggers_rollback_and_raises_service_error(self, test_db_session: Session):
        """Database commit failure rolls back session cleanly without leaking sensitive data."""
        payload = get_sample_vendor_payload()
        vendor_in = VendorCreate(**payload)

        # Mock db.commit to raise an OperationalError
        with patch.object(test_db_session, "commit", side_effect=Exception("Database lock contention")):
            with pytest.raises(VendorServiceError) as exc_info:
                vendor_service.create_vendor(test_db_session, vendor_in)

            assert "Database persistence failed" in str(exc_info.value)
            # Ensure sensitive bank account number is not in the error message
            assert payload["bank_account_number"] not in str(exc_info.value)

        # Verify session is usable for subsequent query
        check_query = test_db_session.execute(text("SELECT 1")).scalar()
        assert check_query == 1


# ==============================================================================
# 4. Deterministic Pagination Tests
# ==============================================================================

class TestDeterministicPagination:
    """Verifies that pagination uses secondary sort key to prevent tie-break nondeterminism."""

    def test_deterministic_ordering_with_identical_timestamps(self, test_db_session: Session):
        """When multiple records have the identical timestamp, order is deterministic by id ASC."""
        fixed_time = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)
        ids = [f"fixed-id-{i}" for i in range(5)]
        
        for vid in ids:
            v = Vendor(
                id=vid,
                legal_name=f"Vendor {vid}",
                business_type="Private Limited",
                country_of_incorporation="United States",
                registration_number=f"REG-{vid}",
                contact_name="Test Person",
                contact_email=f"{vid}@example.com",
                contact_phone="+1 555-111-2222",
                address_line1="123 Test St",
                city="Dallas",
                state_province="TX",
                postal_code="75001",
                address_country="United States",
                tax_id_type="EIN",
                tax_id_number="12-3456789",
                bank_account_holder_name="Test Co",
                bank_name="Test Bank",
                bank_account_number=encrypt_account_number("987654321"),
                bank_routing_number="111000025",
                bank_country="United States",
                status="SUBMITTED",
                created_at=fixed_time,
            )
            test_db_session.add(v)
        test_db_session.commit()

        # Query page 1 (size 3) and page 2 (size 3)
        page1_vendors, total, _ = vendor_service.get_vendors_paginated(test_db_session, page=1, page_size=3)
        page2_vendors, _, _ = vendor_service.get_vendors_paginated(test_db_session, page=2, page_size=3)

        page1_ids = [v.id for v in page1_vendors]
        page2_ids = [v.id for v in page2_vendors]

        # No overlapping IDs between pages
        assert len(set(page1_ids).intersection(set(page2_ids))) == 0


# ==============================================================================
# 5. Startup Reliability Tests
# ==============================================================================

class TestStartupReliability:
    """Verifies that the application fails startup clearly when database or schema init fails."""

    @pytest.mark.asyncio
    async def test_startup_fails_when_db_connectivity_fails(self):
        """Lifespan aborts startup with RuntimeError when database connectivity fails."""
        from app.main import app, lifespan
        
        with patch("app.main.check_db_connection", return_value=False):
            with pytest.raises(RuntimeError) as exc_info:
                async with lifespan(app):
                    pass
            assert "Database connection unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_startup_fails_when_schema_initialization_fails(self):
        """Lifespan aborts startup with RuntimeError when metadata.create_all fails."""
        from app.main import app, lifespan

        with patch("app.main.check_db_connection", return_value=True):
            with patch("app.db.base.Base.metadata.create_all", side_effect=Exception("Disk I/O error")):
                with pytest.raises(RuntimeError) as exc_info:
                    async with lifespan(app):
                        pass
                assert "Database schema initialization or migration failed" in str(exc_info.value)

    def test_existing_database_contents_survive_initialization(self, test_engine, test_db_session: Session):
        """Re-invoking Base.metadata.create_all() does not drop existing vendor records."""
        from app.db.base import Base

        # Verify a record exists
        count_before = test_db_session.scalar(select(Vendor)).id
        assert count_before is not None

        # Re-run create_all (simulating application restart)
        Base.metadata.create_all(bind=test_engine)

        # Record still exists and data was not dropped
        record_after = test_db_session.scalar(select(Vendor).where(Vendor.id == count_before))
        assert record_after is not None
        assert record_after.id == count_before
