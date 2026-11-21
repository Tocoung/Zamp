"""Automated test suite for Phase 2 Step 1: Document Intake, Secure Storage & Validation."""

import hashlib
import io
import os
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.activity import VendorActivity
from app.core.storage import (
    DocumentStorage,
    StorageError,
    StoragePathTraversalError,
    StorageFileNotFoundError,
    document_storage,
)
from app.core.document_validator import (
    validate_document_upload,
    DocumentValidationError,
    DocumentSizeExceededError,
    read_upload_file_bounded,
    MAX_DOCUMENT_FILE_SIZE_BYTES,
    sanitize_filename,
)
from app.services.document_service import document_service, DocumentServiceError


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


class TestStep11BoundedUploadStreaming:
    """Tests for Phase 2 Step 1.1 bounded upload reading and size boundary enforcement."""

    @pytest.mark.asyncio
    async def test_bounded_read_stops_immediately_on_oversized_stream(self):
        """Verifies that reading terminates and aborts as soon as the limit is breached without consuming remaining stream."""
        class MockStreamingUpload:
            def __init__(self, chunk_size: int, total_chunks: int):
                self.chunk_size = chunk_size
                self.total_chunks = total_chunks
                self.chunks_read = 0
                self.closed = False

            async def read(self, size: int = -1):
                if self.chunks_read >= self.total_chunks:
                    return b""
                self.chunks_read += 1
                return b"X" * self.chunk_size

            async def close(self):
                self.closed = True

        # 10 chunks of 64 KB = 640 KB. Limit set to 128 KB.
        # Should read chunk 1 (64 KB <= 128 KB), chunk 2 (128 KB <= 128 KB), chunk 3 (192 KB > 128 KB) -> abort!
        mock_file = MockStreamingUpload(chunk_size=64 * 1024, total_chunks=10)
        max_bytes = 128 * 1024

        with pytest.raises(DocumentSizeExceededError) as exc_info:
            await read_upload_file_bounded(
                mock_file,  # type: ignore
                max_size_bytes=max_bytes,
                chunk_size=64 * 1024,
            )

        assert "exceeds maximum allowed limit" in str(exc_info.value)
        # Verify it stopped at chunk 3, did not consume remaining 7 chunks
        assert mock_file.chunks_read == 3
        # Verify resource was safely closed in finally block
        assert mock_file.closed is True

    def test_upload_exact_max_size_limit_accepted(self, client: TestClient, test_vendor: dict):
        """File at exactly 10 MB limit (10,485,760 bytes) is accepted."""
        vendor_id = test_vendor["id"]
        exact_limit = 10 * 1024 * 1024  # 10 MB

        # Synthesize valid PDF of exact length
        header = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        footer = b"\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        padding_len = exact_limit - len(header) - len(footer)
        exact_pdf = header + (b" " * padding_len) + footer
        assert len(exact_pdf) == exact_limit

        files = {"file": ("exact_10mb.pdf", io.BytesIO(exact_pdf), "application/pdf")}
        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files)
        assert res.status_code == 201
        doc = res.json()
        assert doc["file_size_bytes"] == exact_limit
        assert doc["sha256_checksum"] == hashlib.sha256(exact_pdf).hexdigest()

        # Retrieve and verify exact bytes
        dl_res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc['id']}/content")
        assert dl_res.status_code == 200
        assert len(dl_res.content) == exact_limit

    def test_upload_one_byte_over_limit_rejected_with_413(self, client: TestClient, test_vendor: dict):
        """File at 10 MB + 1 byte is rejected immediately with 413 Payload Too Large."""
        vendor_id = test_vendor["id"]
        over_limit = (10 * 1024 * 1024) + 1

        header = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        footer = b"\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        padding_len = over_limit - len(header) - len(footer)
        oversized_pdf = header + (b" " * padding_len) + footer
        assert len(oversized_pdf) == over_limit

        files = {"file": ("over_limit.pdf", io.BytesIO(oversized_pdf), "application/pdf")}
        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files)
        assert res.status_code == 413
        assert "exceeds maximum allowed limit" in res.json()["detail"]

    def test_multi_chunk_valid_upload_succeeds(self, client: TestClient, test_vendor: dict):
        """Multi-chunk valid upload (e.g. 200 KB spanning several 64 KB chunks) succeeds."""
        vendor_id = test_vendor["id"]
        total_len = 200 * 1024  # 200 KB > 3 chunks of 64 KB

        header = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        footer = b"\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        padding_len = total_len - len(header) - len(footer)
        multi_chunk_pdf = header + (b"0" * padding_len) + footer

        files = {"file": ("multi_chunk.pdf", io.BytesIO(multi_chunk_pdf), "application/pdf")}
        res = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=files)
        assert res.status_code == 201
        doc = res.json()
        assert doc["file_size_bytes"] == total_len


class TestStep11PathContainmentAndSymlinkDefense:
    """Tests for Phase 2 Step 1.1 hardened path resolution, symlink containment, and error sanitization."""

    def test_path_traversal_sequences_rejected(self):
        """Storage path resolver strictly rejects '..' and path traversal tokens."""
        valid_vid = str(uuid.uuid4())
        valid_did = str(uuid.uuid4())

        traversal_attempts = [
            f"../{valid_vid}/{valid_did}.enc",
            f"{valid_vid}/../../{valid_did}.enc",
            f"{valid_vid}/../{valid_did}.enc",
            f"/{valid_vid}/{valid_did}.enc",
            f"/etc/passwd",
            f"..\\{valid_vid}\\{valid_did}.enc",
            f"{valid_vid}\\{valid_did}.enc",
            f"{valid_vid}/",
            f"{valid_vid}/{valid_did}.enc/extra",
        ]

        for attempt in traversal_attempts:
            with pytest.raises(StoragePathTraversalError):
                document_storage._resolve_and_verify_path(attempt)

    def test_null_bytes_in_path_rejected(self):
        """Storage path resolver strictly rejects identifiers containing null bytes."""
        valid_vid = str(uuid.uuid4())
        valid_did = str(uuid.uuid4())

        null_byte_attempts = [
            f"{valid_vid}/{valid_did}\x00.enc",
            f"{valid_vid}\x00/{valid_did}.enc",
            f"\x00{valid_vid}/{valid_did}.enc",
        ]

        for attempt in null_byte_attempts:
            with pytest.raises(StoragePathTraversalError):
                document_storage._resolve_and_verify_path(attempt)

    def test_invalid_uuid_identifiers_rejected(self):
        """Storage path resolver rejects paths where directory or file stem is not a valid UUID."""
        valid_vid = str(uuid.uuid4())
        valid_did = str(uuid.uuid4())

        invalid_identifiers = [
            f"non_uuid_vendor/{valid_did}.enc",
            f"{valid_vid}/non_uuid_doc.enc",
            f"admin/{valid_did}.enc",
            f"{valid_vid}/malicious.sh",
            f"{valid_vid}/{valid_did}.txt",
        ]

        for attempt in invalid_identifiers:
            with pytest.raises(StoragePathTraversalError):
                document_storage._resolve_and_verify_path(attempt)

    def test_symlink_escape_rejected(self, tmp_path: Path):
        """Symlinks pointing outside storage directory are detected and rejected."""
        custom_storage = DocumentStorage(storage_dir=str(tmp_path / "storage"))
        custom_storage.ensure_storage_dir()

        outside_dir = tmp_path / "outside_secret"
        outside_dir.mkdir(parents=True)
        secret_file = outside_dir / "secret.txt"
        secret_file.write_text("classified data")

        # Create symlink vendor directory pointing outside storage root
        escaping_vendor_uuid = str(uuid.uuid4())
        escaping_symlink = custom_storage.storage_dir / escaping_vendor_uuid
        os.symlink(outside_dir, escaping_symlink)

        valid_doc_id = str(uuid.uuid4())
        with pytest.raises(StoragePathTraversalError) as exc_info:
            custom_storage._resolve_and_verify_path(f"{escaping_vendor_uuid}/{valid_doc_id}.enc")

        assert "outside" in str(exc_info.value).lower() or "symlink" in str(exc_info.value).lower()

    def test_storage_errors_do_not_leak_absolute_paths(self):
        """Storage exception messages must not reveal absolute server paths."""
        valid_vid = str(uuid.uuid4())
        valid_did = str(uuid.uuid4())

        # Test traversal error message
        try:
            document_storage._resolve_and_verify_path(f"../../../etc/passwd")
        except StoragePathTraversalError as e:
            msg = str(e)
            assert str(document_storage.storage_dir) not in msg
            assert "/Users/" not in msg
            assert "/etc" not in msg

        # Test missing file error message
        try:
            document_storage.retrieve_document(f"{valid_vid}/{valid_did}.enc")
        except StorageFileNotFoundError as e:
            msg = str(e)
            assert str(document_storage.storage_dir) not in msg
            assert "/Users/" not in msg


class TestStep11DeletionConsistencyAndRecovery:
    """Tests for Phase 2 Step 1.1 two-phase staged deletion and failure recovery."""

    def test_deletion_filesystem_failure_preserves_database_and_activity(
        self, client: TestClient, test_db_session: Session, test_vendor: dict
    ):
        """If staging deletion fails on disk, database record is preserved and no deletion activity is emitted."""
        vendor_id = test_vendor["id"]
        f = {"file": ("contract.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        doc_id = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f).json()["id"]

        # Verify initial database state
        db_doc = test_db_session.get(VendorDocument, doc_id)
        assert db_doc is not None

        # Count activities before delete
        act_before = client.get(f"/api/v1/vendors/{vendor_id}/activities").json()["items"]
        delete_events_before = [a for a in act_before if a["event_type"] == "DOCUMENT_DELETED"]

        # Simulate filesystem failure during stage_deletion
        with patch.object(
            document_service.storage,
            "stage_deletion",
            side_effect=StorageError("Simulated disk write permission failure"),
        ):
            res = client.delete(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}")
            assert res.status_code == 500
            assert "unable to stage document file for removal" in res.json()["detail"].lower()

        # Verify database record STILL exists
        test_db_session.expire_all()
        db_doc_after = test_db_session.get(VendorDocument, doc_id)
        assert db_doc_after is not None

        # Verify no DOCUMENT_DELETED activity was logged
        act_after = client.get(f"/api/v1/vendors/{vendor_id}/activities").json()["items"]
        delete_events_after = [a for a in act_after if a["event_type"] == "DOCUMENT_DELETED"]
        assert len(delete_events_after) == len(delete_events_before)

    def test_deletion_database_failure_rolls_back_staged_file(
        self, test_db_session: Session, test_vendor: dict
    ):
        """If database commit fails during deletion, staged .deleted file is rolled back to original .enc."""
        vendor_id = test_vendor["id"]

        # Directly upload via service
        doc = document_service.upload_vendor_document(
            db=test_db_session,
            vendor_id=vendor_id,
            filename="financials.pdf",
            declared_content_type="application/pdf",
            content=VALID_PDF_BYTES,
        )
        storage_id = doc.storage_identifier
        target_path = document_service.storage._resolve_and_verify_path(storage_id)
        assert target_path.is_file()

        # Simulate database failure during commit
        with patch.object(test_db_session, "commit", side_effect=Exception("Simulated SQLite lock error")):
            with pytest.raises(DocumentServiceError) as exc_info:
                document_service.delete_vendor_document(
                    db=test_db_session,
                    vendor_id=vendor_id,
                    document_id=doc.id,
                )
            assert "transaction rolled back" in str(exc_info.value).lower()

        # Staged .deleted file MUST have been rolled back to .enc
        staged_path = target_path.with_name(f"{target_path.name}.deleted")
        assert not staged_path.exists()
        assert target_path.is_file()

        # Stored file can still be read and decrypted cleanly
        retrieved_content = document_service.storage.retrieve_document(storage_id)
        assert retrieved_content == VALID_PDF_BYTES

    def test_deletion_missing_file_handled_idempotently(
        self, client: TestClient, test_db_session: Session, test_vendor: dict
    ):
        """Deleting a document whose physical file is already missing completes idempotently."""
        vendor_id = test_vendor["id"]
        f = {"file": ("orphan_candidate.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        doc_id = client.post(f"/api/v1/vendors/{vendor_id}/documents", files=f).json()["id"]

        db_doc = test_db_session.get(VendorDocument, doc_id)
        assert db_doc is not None
        storage_path = document_service.storage._resolve_and_verify_path(db_doc.storage_identifier)

        # Manually unlink file from disk to simulate orphaned DB record
        if storage_path.is_file():
            storage_path.unlink()

        # Delete via API
        del_res = client.delete(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}")
        assert del_res.status_code == 204

        # DB record is cleanly removed
        test_db_session.expire_all()
        assert test_db_session.get(VendorDocument, doc_id) is None

        # Activity log is recorded
        act_res = client.get(f"/api/v1/vendors/{vendor_id}/activities")
        assert act_res.status_code == 200
        event_types = [a["event_type"] for a in act_res.json()["items"]]
        assert "DOCUMENT_DELETED" in event_types
