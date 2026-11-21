"""Secure authenticated document storage abstraction with at-rest encryption."""

import hashlib
import os
import uuid
from pathlib import Path
from typing import Optional, Union
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
        storage_dir: Optional[Union[str, Path]] = None,
        custom_key: Optional[str] = None,
    ):
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir).resolve()
        else:
            self.storage_dir = Path(settings.resolved_document_storage_dir).resolve()
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
        
        Guarantees:
        - Generated UUID-based identifiers remain the only identifiers used to construct storage paths.
        - Resolved paths remain inside the configured storage root.
        - Symlinks cannot be used to escape the storage root.
        - Invalid, manipulated, or absolute identifiers fail safely.
        - Errors do not disclose absolute filesystem paths.
        """
        if not storage_identifier or not str(storage_identifier).strip():
            raise StoragePathTraversalError("Storage identifier cannot be empty.")

        raw_id = str(storage_identifier).strip()

        # 1. Reject null bytes, backslashes, and absolute paths immediately
        if "\x00" in raw_id:
            raise StoragePathTraversalError("Invalid storage identifier: null bytes detected.")

        if "\\" in raw_id:
            raise StoragePathTraversalError("Backslash path separators are forbidden in storage identifiers.")

        if raw_id.startswith("/") or Path(raw_id).is_absolute():
            raise StoragePathTraversalError("Absolute paths are forbidden in storage identifiers.")

        clean_id = raw_id

        # 2. Reject traversal sequences ("..")
        parts = clean_id.split("/")
        if any(p in ("..", ".", "") for p in parts):
            raise StoragePathTraversalError("Directory traversal sequences are forbidden.")

        # 3. Enforce two-component layout: <vendor_id>/<doc_id_with_extension>
        if len(parts) != 2:
            raise StoragePathTraversalError("Storage identifier must have format '<vendor_id>/<filename>'.")

        vendor_part, file_part = parts[0], parts[1]

        # 4. Enforce UUID structure for vendor and document stem
        try:
            uuid.UUID(vendor_part)
        except ValueError as e:
            raise StoragePathTraversalError("Invalid vendor identifier format in storage path.") from e

        # Extract stem before allowed extensions (.enc.deleted, .enc, .tmp)
        doc_stem = file_part
        allowed_suffixes = (".enc.deleted", ".enc", ".tmp")
        matched_suffix = False
        for sfx in allowed_suffixes:
            if doc_stem.endswith(sfx):
                doc_stem = doc_stem[:-len(sfx)]
                matched_suffix = True
                break

        if not matched_suffix:
            raise StoragePathTraversalError("Invalid document file extension in storage path.")

        try:
            uuid.UUID(doc_stem)
        except ValueError as e:
            raise StoragePathTraversalError("Invalid document identifier format in storage path.") from e

        # 5. Verify physical path containment & symlink escape prevention
        root_path = Path(os.path.realpath(self.storage_dir))
        raw_target = self.storage_dir / clean_id
        real_target = Path(os.path.realpath(raw_target))

        # Check containment via relative_to
        try:
            real_target.relative_to(root_path)
        except ValueError as e:
            logger.warning("Security violation: Storage path or symlink escapes storage root.")
            raise StoragePathTraversalError("Storage path is outside the allowed directory.") from e

        # Ensure target is not the root directory itself
        if real_target == root_path:
            raise StoragePathTraversalError("Storage identifier cannot resolve to the root directory.")

        # Check if parent directory or target itself is an escaping symlink
        check = self.storage_dir
        for part in parts:
            check = check / part
            if check.is_symlink():
                real_link = Path(os.path.realpath(check))
                try:
                    real_link.relative_to(root_path)
                except ValueError as e:
                    logger.warning("Security violation: Symlink inside storage directory escapes root: %s", part)
                    raise StoragePathTraversalError("Symlink escape detected in storage path.") from e

        return raw_target

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
            logger.error("Failed to write encrypted document to disk: %s", type(e).__name__)
            raise StorageError(f"Failed to write encrypted document to disk: {type(e).__name__}") from e

        # Relative storage identifier (never exposes absolute server paths)
        storage_id = f"{vendor_id}/{document_id}.enc"
        return storage_id

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
            raise StorageFileNotFoundError("Document file not found on storage.")

        try:
            encrypted_bytes = target_path.read_bytes()
        except Exception as e:
            logger.error("Failed to read document file: %s", type(e).__name__)
            raise StorageError(f"Failed to read document from storage: {type(e).__name__}") from e

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

    def stage_deletion(self, storage_identifier: str) -> Optional[Path]:
        """Atomically stage a document file for deletion on disk (renaming to .deleted).
        
        Guarantees:
        - Atomic rename prevents partial reads or race conditions during deletion.
        - Missing files return None without error, enabling idempotent recovery.
        - Filesystem errors (e.g. PermissionError) raise StorageError before DB mutation.
        
        Returns:
            Path to staged file, or None if the file was already absent on disk.
        """
        target_path = self._resolve_and_verify_path(storage_identifier)
        staged_path = target_path.with_name(f"{target_path.name}.deleted")

        if not target_path.is_file():
            if staged_path.is_file():
                return staged_path
            return None

        try:
            target_path.replace(staged_path)
            return staged_path
        except Exception as e:
            logger.error("Failed to stage physical document file for deletion: %s", type(e).__name__)
            raise StorageError(f"Disk deletion staging failed: {type(e).__name__}") from e

    def rollback_staged_deletion(self, storage_identifier: str) -> bool:
        """Roll back a staged deletion by restoring the staged .deleted file to .enc."""
        try:
            target_path = self._resolve_and_verify_path(storage_identifier)
            staged_path = target_path.with_name(f"{target_path.name}.deleted")
            if staged_path.is_file():
                staged_path.replace(target_path)
                logger.info("Successfully rolled back staged document deletion: %s", storage_identifier)
                return True
            return False
        except Exception as e:
            logger.error("Failed to rollback staged deletion for %s: %s", storage_identifier, type(e).__name__)
            return False

    def finalize_staged_deletion(self, storage_identifier: str) -> bool:
        """Permanently unlink the staged .deleted file and clean up empty parent directories."""
        try:
            target_path = self._resolve_and_verify_path(storage_identifier)
            staged_path = target_path.with_name(f"{target_path.name}.deleted")

            if staged_path.is_file():
                staged_path.unlink()
            elif target_path.is_file():
                target_path.unlink()

            # Clean up empty vendor directory if no other documents remain
            vendor_dir = target_path.parent
            if vendor_dir != self.storage_dir and vendor_dir.is_dir():
                try:
                    if not any(vendor_dir.iterdir()):
                        vendor_dir.rmdir()
                except OSError:
                    pass
            return True
        except Exception as e:
            logger.error("Failed to finalize staged deletion for %s: %s", storage_identifier, type(e).__name__)
            return False

    def delete_document(self, storage_identifier: str, ignore_missing: bool = True) -> bool:
        """Safely delete a stored document file from disk using staged deletion.
        
        Args:
            storage_identifier: Relative identifier of file to delete.
            ignore_missing: If True, absent files are treated idempotently as success.
            
        Returns:
            True if file was deleted or was already absent (when ignore_missing=True).
        """
        staged_path = self.stage_deletion(storage_identifier)
        if staged_path is None:
            if not ignore_missing:
                raise StorageFileNotFoundError("Document file not found on storage.")
            return True
        return self.finalize_staged_deletion(storage_identifier)

    @staticmethod
    def calculate_sha256(content: bytes) -> str:
        """Compute the SHA-256 hex digest of a byte sequence."""
        return hashlib.sha256(content).hexdigest()


# Singleton default storage instance
document_storage = DocumentStorage()
