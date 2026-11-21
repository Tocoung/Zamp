"""Security and cryptography utilities for sensitive data encryption at rest."""

from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger

ENCRYPTION_VERSION_PREFIX = "enc:v1:"


class EncryptionError(Exception):
    """Base exception for encryption and decryption errors."""
    pass


class EncryptionConfigurationError(EncryptionError):
    """Raised when the encryption key is missing or invalid."""
    pass


class DecryptionError(EncryptionError):
    """Raised when decryption fails due to corrupted ciphertext or incorrect key."""
    pass


def get_fernet_cipher(custom_key: Optional[str] = None) -> Fernet:
    """Instantiates and returns an authenticated Fernet cipher instance.
    
    Args:
        custom_key: Optional 32-byte URL-safe base64 key override (useful for testing).
                    If None, reads from settings.VENDOR_DATA_ENCRYPTION_KEY.
                    
    Raises:
        EncryptionConfigurationError: If the key is missing or malformed.
    """
    key = custom_key or settings.VENDOR_DATA_ENCRYPTION_KEY
    if not key or not str(key).strip():
        raise EncryptionConfigurationError(
            "VENDOR_DATA_ENCRYPTION_KEY is not configured. "
            "Data encryption at rest requires a valid Fernet key in the environment."
        )

    try:
        clean_key = str(key).strip()
        return Fernet(clean_key.encode("utf-8"))
    except Exception as e:
        raise EncryptionConfigurationError(
            f"Invalid VENDOR_DATA_ENCRYPTION_KEY: {type(e).__name__}. "
            "Key must be a valid 32-byte URL-safe base64-encoded string."
        ) from e


def is_encrypted(value: Optional[str]) -> bool:
    """Returns True if the given value starts with the versioned encryption prefix."""
    if not value or not isinstance(value, str):
        return False
    return value.startswith(ENCRYPTION_VERSION_PREFIX)


def encrypt_account_number(
    plain_account: Optional[str], custom_key: Optional[str] = None
) -> str:
    """Encrypts a bank account number at rest using authenticated Fernet (AES-128-CBC + HMAC-SHA256).
    
    Returns a versioned ciphertext string: 'enc:v1:<fernet_token>'.
    Idempotent: If value is already encrypted with enc:v1:, returns it unmodified.
    
    Raises:
        EncryptionConfigurationError: If the encryption key is missing or invalid.
        EncryptionError: If account number is empty or encryption fails.
    """
    if not plain_account or not str(plain_account).strip():
        raise EncryptionError("Cannot encrypt an empty or null bank account number.")

    clean_account = str(plain_account).strip()
    if is_encrypted(clean_account):
        return clean_account  # Idempotent guard

    cipher = get_fernet_cipher(custom_key=custom_key)
    try:
        encrypted_token = cipher.encrypt(clean_account.encode("utf-8")).decode("utf-8")
        return f"{ENCRYPTION_VERSION_PREFIX}{encrypted_token}"
    except Exception as e:
        # Never include raw account numbers in error messages
        raise EncryptionError(f"Encryption failed: {type(e).__name__}") from e


def decrypt_account_number(
    stored_value: Optional[str],
    allow_legacy_plaintext: bool = False,
    custom_key: Optional[str] = None,
) -> str:
    """Decrypts a stored bank account number.
    
    Args:
        stored_value: Stored value from the database (either 'enc:v1:<token>' or legacy plaintext).
        allow_legacy_plaintext: If True, unencrypted legacy values are returned as-is (for migration).
                                If False, non-prefixed values raise a DecryptionError.
        custom_key: Optional key override for testing.
        
    Returns:
        The decrypted plaintext account number string.
        
    Raises:
        DecryptionError: If ciphertext is corrupted or unencrypted when legacy is disallowed.
        EncryptionConfigurationError: If key is missing or invalid.
    """
    if not stored_value or not str(stored_value).strip():
        raise DecryptionError("Cannot decrypt empty or null value.")

    clean_value = str(stored_value).strip()

    if is_encrypted(clean_value):
        cipher = get_fernet_cipher(custom_key=custom_key)
        token = clean_value[len(ENCRYPTION_VERSION_PREFIX):]
        try:
            decrypted_bytes = cipher.decrypt(token.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken as e:
            raise DecryptionError(
                "Failed to decrypt bank account number: Corrupted ciphertext or invalid key."
            ) from e
        except Exception as e:
            raise DecryptionError(f"Decryption failed: {type(e).__name__}") from e

    # Value does NOT start with versioned encryption prefix
    if allow_legacy_plaintext:
        return clean_value

    raise DecryptionError(
        "Stored bank account number is not in encrypted format (missing 'enc:v1:' prefix). "
        "Run the legacy database migration to encrypt existing records."
    )


def migrate_legacy_vendor_accounts(db: Session, custom_key: Optional[str] = None) -> int:
    """Idempotently scans the database and encrypts any legacy plaintext vendor bank account numbers.
    
    Never prints or logs sensitive account numbers.
    Rolls back transaction on any failure.
    
    Returns:
        Number of vendor records migrated.
    """
    from app.models.vendor import Vendor

    # Verify cipher configuration first
    cipher = get_fernet_cipher(custom_key=custom_key)

    try:
        # Fetch all vendors
        vendors = list(db.scalars(select(Vendor)).all())
        migrated_count = 0

        for vendor in vendors:
            current_val = vendor.bank_account_number
            if current_val and not is_encrypted(current_val):
                # Encrypt plaintext record
                encrypted_val = encrypt_account_number(current_val, custom_key=custom_key)
                vendor.bank_account_number = encrypted_val
                migrated_count += 1

        if migrated_count > 0:
            db.commit()
            logger.info(f"Successfully migrated {migrated_count} legacy vendor account(s) to encrypted format.")
        else:
            logger.info("No legacy plaintext vendor account records required migration.")

        return migrated_count

    except Exception as e:
        db.rollback()
        logger.error(f"Legacy account encryption migration failed: {type(e).__name__}")
        raise EncryptionError(f"Database migration failed: {type(e).__name__}") from e
