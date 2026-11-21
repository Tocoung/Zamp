"""Automated test suite for Phase 2 Step 1: Document Intake, Secure Storage & Validation."""

import hashlib
import io
import uuid
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.activity import VendorActivity
from app.core.storage import DocumentStorage, StorageError
from app.core.document_validator import validate_document_upload, DocumentValidationError, sanitize_filename


# Valid synthetic binary payloads with authentic magic signatures
VALID_PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
VALID_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
VALID_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9"


@pytest.fixture
def test_vendor(client: TestClient) -> dict:
    """Creates a temporary registered vendor for document testing."""
    unique_reg = f"U72200DL2024PTC{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "legal_name": "Apex Document Technologies Pvt Ltd",
        "trade_name": "Apex DocTech",
        "business_type": "Private Limited",
        "country_of_incorporation": "India",
        "registration_number": unique_reg,
        "contact_name": "Kavita Rao",
        "contact_email": f"kavita.{uuid.uuid4().hex[:4]}@apexdoctech.com",
        "contact_phone": "+919876543210",
        "address_line1": "Level 5, Cyberspace Tower",
        "address_line2": "Sector 62",
        "city": "Noida",
        "state_province": "Uttar Pradesh",
        "postal_code": "201301",
        "address_country": "India",
        "tax_id_type": "GSTIN",
        "tax_id_number": "09AAACA1234A1Z5",
        "bank_account_holder_name": "Apex Document Technologies Pvt Ltd",
        "bank_name": "ICICI Bank",
        "bank_account_number": "002105001234",
        "bank_routing_number": "ICIC0000021",
        "bank_country": "India",
    }
    res = client.post("/api/v1/vendors", json=payload)
    assert res.status_code == 201
    return res.json()


@pytest.fixture
def second_vendor(client: TestClient) -> dict:
    """Creates a second distinct vendor for cross-vendor authorization isolation testing."""
    unique_reg = f"U72200MH2024PTC{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "legal_name": "Separate Entity Corp",
        "trade_name": "Separate Entity",
        "business_type": "Private Limited",
        "country_of_incorporation": "India",
        "registration_number": unique_reg,
        "contact_name": "Rohan Deshmukh",
        "contact_email": f"rohan.{uuid.uuid4().hex[:4]}@separateentity.com",
        "contact_phone": "+919123456789",
        "address_line1": "Nariman Point",
        "city": "Mumbai",
        "state_province": "Maharashtra",
        "postal_code": "400021",
        "address_country": "India",
        "tax_id_type": "GSTIN",
        "tax_id_number": "27AAACS9999Z1Z1",
        "bank_account_holder_name": "Separate Entity Corp",
        "bank_name": "Axis Bank",
        "bank_account_number": "918020012345678",
        "bank_routing_number": "UTIB0000004",
        "bank_country": "India",
    }
    res = client.post("/api/v1/vendors", json=payload)
    assert res.status_code == 201
    return res.json()


class TestDocumentIntakeAndUpload:
    """Tests for document upload security, validation, and metadata persistence."""

    def test_upload_valid_pdf_success(self, client: TestClient, test_vendor: dict):
        """Valid PDF upload succeeds with 201 Created and correct sanitized metadata."""
        vendor_id = test_vendor["id"]
        files = {"file": ("incorporation_certificate.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        data = {"document_category": "CERTIFICATE_OF_INCORPORATION"}

        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files, data=data)
        assert res.status_code == 201
        doc = res.json()

        assert doc["vendor_id"] == vendor_id
        assert doc["original_filename"] == "incorporation_certificate.pdf"
        assert doc["sanitized_filename"] == "incorporation_certificate.pdf"
        assert doc["document_category"] == "CERTIFICATE_OF_INCORPORATION"
        assert doc["mime_type"] == "application/pdf"
        assert doc["file_extension"] == ".pdf"
        assert doc["file_size_bytes"] == len(VALID_PDF_BYTES)
        assert doc["upload_status"] == "UPLOADED"
        assert doc["document_version"] == 1
        assert doc["sha256_checksum"] == hashlib.sha256(VALID_PDF_BYTES).hexdigest()
        assert "storage_identifier" not in doc  # Strict security check: internal storage path is NOT exposed

    def test_upload_valid_png_success(self, client: TestClient, test_vendor: dict):
        """Valid PNG upload succeeds with canonical MIME and version tracking."""
        vendor_id = test_vendor["id"]
        files = {"file": ("voided_cheque.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
        data = {"document_category": "BANK_PROOF"}

        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files, data=data)
        assert res.status_code == 201
        doc = res.json()

        assert doc["document_category"] == "BANK_PROOF"
        assert doc["mime_type"] == "image/png"
        assert doc["file_extension"] == ".png"
        assert doc["file_size_bytes"] == len(VALID_PNG_BYTES)

    def test_upload_valid_jpeg_success(self, client: TestClient, test_vendor: dict):
        """Valid JPEG upload succeeds with canonical MIME."""
        vendor_id = test_vendor["id"]
        files = {"file": ("tax_card.jpg", io.BytesIO(VALID_JPEG_BYTES), "image/jpeg")}
        data = {"document_category": "TAX_CERTIFICATE"}

        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files, data=data)
        assert res.status_code == 201
        doc = res.json()

        assert doc["document_category"] == "TAX_CERTIFICATE"
        assert doc["mime_type"] == "image/jpeg"
        assert doc["file_extension"] == ".jpg"

    def test_upload_multiple_versions_increments_version(self, client: TestClient, test_vendor: dict):
        """Uploading multiple documents in the same category correctly increments document_version."""
        vendor_id = test_vendor["id"]

        # First upload
        f1 = {"file": ("bank_statement_v1.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        r1 = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f1, data={"document_category": "BANK_PROOF"})
        assert r1.status_code == 201
        assert r1.json()["document_version"] == 1

        # Second upload in same category
        f2 = {"file": ("bank_statement_v2.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        r2 = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f2, data={"document_category": "BANK_PROOF"})
        assert r2.status_code == 201
        assert r2.json()["document_version"] == 2

    def test_upload_nonexistent_vendor_returns_404(self, client: TestClient):
        """Upload for a nonexistent vendor returns 404 Not Found."""
        random_id = str(uuid.uuid4())
        files = {"file": ("cert.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        res = client.post(f"/api/v1/vendors/{random_id}/documents", files=files)
        assert res.status_code == 404
        assert f"Vendor with ID '{random_id}' not found" in res.json()["detail"]

    def test_upload_empty_file_rejected(self, client: TestClient, test_vendor: dict):
        """Empty file (0 bytes) is rejected with 400 Bad Request."""
        vendor_id = test_vendor["id"]
        files = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files)
        assert res.status_code == 400
        assert "File is empty" in res.json()["detail"]

    def test_upload_oversized_file_rejected(self, client: TestClient, test_vendor: dict):
        """File exceeding 10 MB limit is rejected with 413 Payload Too Large."""
        vendor_id = test_vendor["id"]
        # Simulate oversized payload (11 MB)
        oversized_bytes = VALID_PDF_BYTES + b"0" * (11 * 1024 * 1024)
        files = {"file": ("huge_scan.pdf", io.BytesIO(oversized_bytes), "application/pdf")}
        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files)
        assert res.status_code == 413
        assert "exceeds maximum allowed limit" in res.json()["detail"]

    def test_upload_unsupported_extension_rejected(self, client: TestClient, test_vendor: dict):
        """Uploading files with unauthorized extensions (.exe, .docx, .zip) is rejected."""
        vendor_id = test_vendor["id"]
        files = {"file": ("payload.exe", io.BytesIO(b"MZ\x90\x00fake_binary"), "application/x-msdownload")}
        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files)
        assert res.status_code == 400
        assert "forbidden for security reasons" in res.json()["detail"] or "Unsupported" in res.json()["detail"]

    def test_upload_mime_signature_mismatch_rejected(self, client: TestClient, test_vendor: dict):
        """Uploading plain text or executable masked with a .pdf extension is rejected by signature check."""
        vendor_id = test_vendor["id"]
        fake_pdf = b"<html><script>alert(1)</script></html>"
        files = {"file": ("exploit.pdf", io.BytesIO(fake_pdf), "application/pdf")}
        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files)
        assert res.status_code == 400
        assert "does not match a supported binary signature" in res.json()["detail"]

    def test_upload_path_traversal_filename_sanitized(self, client: TestClient, test_vendor: dict):
        """Path traversal sequences in original filename are sanitized and cannot manipulate storage path."""
        vendor_id = test_vendor["id"]
        malicious_filename = "../../../etc/passwd.pdf"
        files = {"file": (malicious_filename, io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files)
        assert res.status_code == 201
        doc = res.json()
        assert doc["sanitized_filename"] == "passwd.pdf"
        assert "/" not in doc["sanitized_filename"]
        assert ".." not in doc["sanitized_filename"]


class TestDocumentRetrievalAndDownload:
    """Tests for document listing, individual metadata retrieval, and decrypted streaming."""

    def test_list_vendor_documents_with_pagination_and_filter(self, client: TestClient, test_vendor: dict):
        """Listing documents returns paginated records and supports category filtering."""
        vendor_id = test_vendor["id"]

        # Upload tax doc and address doc
        f1 = {"file": ("tax_cert.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f1, data={"document_category": "TAX_CERTIFICATE"})

        f2 = {"file": ("utility_bill.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
        client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f2, data={"document_category": "ADDRESS_PROOF"})

        # List all
        list_res = client.get(f"/api/v1/vendors/{vendor_id}/documents")
        assert list_res.status_code == 200
        data = list_res.json()
        assert data["total"] >= 2
        assert len(data["items"]) >= 2

        # List filtered by category
        filtered_res = client.get(f"/api/v1/vendors/{vendor_id}/documents?category=TAX_CERTIFICATE")
        assert filtered_res.status_code == 200
        filtered_data = filtered_res.json()
        for item in filtered_data["items"]:
            assert item["document_category"] == "TAX_CERTIFICATE"

    def test_retrieve_document_metadata_success(self, client: TestClient, test_vendor: dict):
        """GET /vendors/{id}/documents/{doc_id} retrieves accurate document metadata."""
        vendor_id = test_vendor["id"]
        f = {"file": ("meta_test.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        up_res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f)
        doc_id = up_res.json()["id"]

        meta_res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}")
        assert meta_res.status_code == 200
        meta = meta_res.json()
        assert meta["id"] == doc_id
        assert meta["sanitized_filename"] == "meta_test.pdf"

    def test_download_document_content_reproduces_exact_bytes(self, client: TestClient, test_vendor: dict):
        """GET /vendors/{id}/documents/{doc_id}/content streams exact decrypted original bytes with safe headers."""
        vendor_id = test_vendor["id"]
        f = {"file": ("download_test.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        up_res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f)
        doc_id = up_res.json()["id"]

        dl_res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/content")
        assert dl_res.status_code == 200
        assert dl_res.content == VALID_PDF_BYTES
        assert dl_res.headers["content-type"] == "application/pdf"
        assert 'attachment; filename="download_test.pdf"' in dl_res.headers["content-disposition"]
        assert dl_res.headers["x-content-type-options"] == "nosniff"

    def test_cross_vendor_document_access_rejected(
        self, client: TestClient, test_vendor: dict, second_vendor: dict
    ):
        """Querying or downloading vendor A's document with vendor B's ID returns 404."""
        v1_id = test_vendor["id"]
        v2_id = second_vendor["id"]

        # Upload under vendor 1
        f = {"file": ("private_v1.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        up_res = client.post(f"/api/v1/vendors/{v1_id}/documents", files=f)
        doc_id = up_res.json()["id"]

        # Attempt to access via vendor 2 ID
        cross_meta = client.get(f"/api/v1/vendors/{v2_id}/documents/{doc_id}")
        assert cross_meta.status_code == 404

        cross_dl = client.get(f"/api/v1/vendors/{v2_id}/documents/{doc_id}/content")
        assert cross_dl.status_code == 404


class TestDocumentDeletionAndLifecycle:
    """Tests for document deletion, physical file cleanup, and activity timeline logging."""

    def test_delete_document_success_and_removes_from_disk(
        self, client: TestClient, test_db_session: Session, test_vendor: dict
    ):
        """Deleting a document removes metadata, deletes encrypted file, and logs lifecycle event."""
        vendor_id = test_vendor["id"]

        # Upload document
        f = {"file": ("delete_me.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        up_res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f, data={"document_category": "OTHER"})
        doc_id = up_res.json()["id"]

        # Verify exists in database
        db_doc = test_db_session.get(VendorDocument, doc_id)
        assert db_doc is not None
        storage_id = db_doc.storage_identifier

        # Delete document
        del_res = client.delete(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}")
        assert del_res.status_code == 204

        # Confirm metadata removed
        test_db_session.expire_all()
        assert test_db_session.get(VendorDocument, doc_id) is None

        # Confirm 404 on subsequent get
        assert client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}").status_code == 404

        # Confirm lifecycle activity recorded
        act_res = client.get(f"/api/v1/vendors/{vendor_id}/activities")
        assert act_res.status_code == 200
        event_types = [a["event_type"] for a in act_res.json()["items"]]
        assert "DOCUMENT_UPLOADED" in event_types
        assert "DOCUMENT_DELETED" in event_types

        # Verify no sensitive data in activity description
        for act in act_res.json()["items"]:
            if act["event_type"] in ("DOCUMENT_UPLOADED", "DOCUMENT_DELETED"):
                assert "storage" not in act["description"].lower()
                assert ".enc" not in act["description"]

    def test_delete_one_document_leaves_unrelated_documents_intact(
        self, client: TestClient, test_vendor: dict
    ):
        """Deleting one document does not affect other documents of the same vendor."""
        vendor_id = test_vendor["id"]

        # Upload two documents
        f1 = {"file": ("doc_a.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        doc_a_id = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f1).json()["id"]

        f2 = {"file": ("doc_b.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
        doc_b_id = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f2).json()["id"]

        # Delete doc A
        client.delete(f"/api/v1/vendors/{vendor_id}/documents/{doc_a_id}")

        # Confirm doc A is gone
        assert client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_a_id}").status_code == 404

        # Confirm doc B is still fully intact and downloadable
        b_res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_b_id}/content")
        assert b_res.status_code == 200
        assert b_res.content == VALID_PNG_BYTES


class TestDocumentSecurityAndStorageAtRest:
    """Tests verifying authenticated encryption at rest and path containment."""

    def test_stored_file_is_encrypted_at_rest(
        self, client: TestClient, test_db_session: Session, test_vendor: dict
    ):
        """Verifies physical file on disk does not contain raw plaintext and begins with Fernet token."""
        vendor_id = test_vendor["id"]
        f = {"file": ("confidential.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        doc_id = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f).json()["id"]

        db_doc = test_db_session.get(VendorDocument, doc_id)
        assert db_doc is not None

        # Resolve storage file path
        from app.core.storage import document_storage
        storage_path = document_storage._resolve_and_verify_path(db_doc.storage_identifier)
        assert storage_path.is_file()

        raw_disk_bytes = storage_path.read_bytes()
        # Raw plaintext is strictly NOT in the stored file
        assert VALID_PDF_BYTES not in raw_disk_bytes
        # Stored file begins with standard Fernet header byte 0x80 (128)
        assert raw_disk_bytes.startswith(b"\x80") or raw_disk_bytes.startswith(b"gAAAAA")

    def test_corrupted_file_raises_safe_500(
        self, client: TestClient, test_db_session: Session, test_vendor: dict
    ):
        """Corrupting stored ciphertext on disk causes download endpoint to return safe 500."""
        vendor_id = test_vendor["id"]
        f = {"file": ("corrupt_test.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        doc_id = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f).json()["id"]

        db_doc = test_db_session.get(VendorDocument, doc_id)
        from app.core.storage import document_storage
        storage_path = document_storage._resolve_and_verify_path(db_doc.storage_identifier)

        # Corrupt file contents directly on disk
        storage_path.write_bytes(b"invalid_corrupted_ciphertext_12345")

        dl_res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/content")
        assert dl_res.status_code == 500
        assert "decryption failed" in dl_res.json()["detail"].lower()
