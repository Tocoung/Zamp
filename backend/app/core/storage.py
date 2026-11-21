"""Secure authenticated document storage abstraction with at-rest encryption."""

import hashlib
import os
import uuid
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.security import get_fernet_cipher, EncryptionError, EncryptionConfigurationError
from app.core.logging import logger


class StorageError(EncryptionError):
    """Base exception for document storage operations."""
    pass


class StoragePathTraversalError(StorageError):
    """Raised when an attempted storage path violates root directory boundaries."""
    pass


class StorageFileNotFoundError(StorageError):
    """Raised when a requested stored document does not exist on disk."""
    pass


class StorageDecryptionError(StorageError):
    """Raised when a stored document cannot be decrypted (corrupted ciphertext or invalid key)."""
    pass


class DocumentStorage:
    """Manages encrypted document persistence, atomic file writes, and path containment."""

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        custom_key: Optional[str] = None,
    ):
        self.storage_dir = (storage_dir or settings.resolved_document_storage_dir).resolve()
        self.custom_key = custom_key
        self._cipher: Optional[Fernet] = None

    @property
    def cipher(self) -> Fernet:
        """Lazily initialize and validate the authenticated encryption cipher."""
        if self._cipher is None:
            key = self.custom_key or settings.DOCUMENT_ENCRYPTION_KEY or settings.VENDOR_DATA_ENCRYPTION_KEY
            if not key or not str(key).strip():
                raise EncryptionConfigurationError(
                    "No encryption key configured for document storage. "
                    "Set DOCUMENT_ENCRYPTION_KEY or VENDOR_DATA_ENCRYPTION_KEY in the environment."
                )
            self._cipher = get_fernet_cipher(custom_key=key)
        return self._cipher

    def ensure_storage_dir(self) -> Path:
        """Create the root storage directory if it does not exist."""
        self.storage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        return self.storage_dir

    def _resolve_and_verify_path(self, storage_identifier: str) -> Path:
        """Resolve a relative storage identifier and verify path containment.
        
        Strictly prevents directory traversal attempts.
        """
        if not storage_identifier or not str(storage_identifier).strip():
            raise StoragePathTraversalError("Storage identifier cannot be empty.")

        # Clean string identifier
        clean_id = str(storage_identifier).strip().replace("\\", "/")
        target_path = (self.storage_dir / clean_id).resolve()
        root_path = self.storage_dir.resolve()

        try:
            target_path.relative_to(root_path)
        except ValueError as e:
            logger.warning(
                "Security violation: Directory traversal attempt detected: identifier=%r",
                storage_identifier,
            )
            raise StoragePathTraversalError("Storage path is outside the allowed directory.") from e

        return target_path

    def store_document(
        self,
        vendor_id: str,
        document_id: str,
        content: bytes,
    ) -> str:
        """Encrypt and atomically store a document blob outside the webroot.
        
        Args:
            vendor_id: Associated vendor UUID string.
            document_id: Generated document UUID string.
            content: Raw plaintext file bytes.
            
        Returns:
            Relative storage identifier string (e.g., '{vendor_id}/{document_id}.enc').
        """
        # Validate UUID structure to strictly guarantee clean path construction
        try:
            uuid.UUID(str(vendor_id))
            uuid.UUID(str(document_id))
        except ValueError as e:
            raise StorageError(f"Invalid UUID provided for storage path: {e}") from e

        self.ensure_storage_dir()
        vendor_dir = (self.storage_dir / str(vendor_id)).resolve()
        vendor_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        target_file = vendor_dir / f"{document_id}.enc"
        temp_file = vendor_dir / f"{document_id}.tmp"

        # Encrypt with authenticated Fernet cipher
        try:
            encrypted_payload = self.cipher.encrypt(content)
        except Exception as e:
            raise StorageError(f"Failed to encrypt document contents: {type(e).__name__}") from e

        # Atomic write pattern: write to temporary file, flush, then atomic replace
        try:
            temp_file.write_bytes(encrypted_payload)
            temp_file.replace(target_file)
        except Exception as e:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise StorageError(f"Failed to write encrypted document to disk: {e}") from e

        # Relative storage identifier (never exposes absolute server paths)
        return f"{vendor_id}/{document_id}.enc"

    def retrieve_document(self, storage_identifier: str) -> bytes:
        """Locate, read, and decrypt a stored document blob.
        
        Args:
            storage_identifier: Relative identifier returned by store_document.
            
        Returns:
            Original plaintext bytes.
            
        Raises:
            StorageFileNotFoundError: If the encrypted file does not exist.
            StorageDecryptionError: If decryption fails (corrupted file or wrong key).
            StoragePathTraversalError: If the identifier attempts directory traversal.
        """
        target_path = self._resolve_and_verify_path(storage_identifier)

        if not target_path.is_file():
            raise StorageFileNotFoundError(f"Document file not found on disk: {storage_identifier}")

        try:
            encrypted_bytes = target_path.read_bytes()
        except Exception as e:
            raise StorageError(f"Failed to read document from disk: {e}") from e

        try:
            return self.cipher.decrypt(encrypted_bytes)
        except InvalidToken as e:
            logger.error(
                "Cryptographic error: Stored document ciphertext corrupted or invalid key: identifier=%s",
                storage_identifier,
            )
            raise StorageDecryptionError(
                "Document could not be decrypted. The file may be corrupted or the encryption key is incorrect."
            ) from e
        except Exception as e:
            raise StorageDecryptionError(f"Unexpected decryption failure: {type(e).__name__}") from e

    def delete_document(self, storage_identifier: str) -> bool:
        """Safely delete a stored document file from disk.
        
        Args:
            storage_identifier: Relative identifier of file to delete.
            
        Returns:
            True if file existed and was unlinked, False if file did not exist.
        """
        try:
            target_path = self._resolve_and_verify_path(storage_identifier)
        except StoragePathTraversalError:
            return False

        if not target_path.is_file():
            return False

        try:
            target_path.unlink()
            # Attempt to clean up empty vendor folder if no other documents remain
            vendor_dir = target_path.parent
            if vendor_dir != self.storage_dir and vendor_dir.is_dir():
                try:
                    if not any(vendor_dir.iterdir()):
                        vendor_dir.rmdir()
                except OSError:
                    pass
            return True
        except Exception as e:
            logger.error("Failed to delete document file from disk: %s", e)
            raise StorageError(f"Disk cleanup failed: {e}") from e

    @staticmethod
    def calculate_sha256(content: bytes) -> str:
        """Compute the SHA-256 hex digest of a byte sequence."""
        return hashlib.sha256(content).hexdigest()


# Singleton default storage instance
document_storage = DocumentStorage()
