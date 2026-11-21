"""Strict file content, magic byte, and filename validation for vendor document intake."""

import os
import re
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

from app.core.config import settings

MAX_DOCUMENT_FILE_SIZE_BYTES: int = getattr(settings, "MAX_DOCUMENT_FILE_SIZE_BYTES", 10 * 1024 * 1024)


class DocumentValidationError(ValueError):
    """Raised when an uploaded document violates size, format, or security constraints."""
    pass


class DocumentSizeExceededError(DocumentValidationError):
    """Raised when an uploaded document exceeds the maximum allowed file size."""
    pass


# Magic byte signatures for authorized file types
MAGIC_SIGNATURES = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpeg": [b"\xff\xd8\xff"],
}

ALLOWED_EXTENSIONS_MAP: Dict[str, str] = {
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
}

ALLOWED_MIME_TYPES_MAP: Dict[str, str] = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
}

CANONICAL_MIME_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpeg": "image/jpeg",
}

DISALLOWED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".bash", ".php", ".py", ".rb", ".js", ".ts",
    ".html", ".htm", ".xhtml", ".svg", ".xml", ".jar", ".zip", ".tar", ".gz",
    ".7z", ".rar", ".msi", ".dll", ".so", ".dylib", ".vbs", ".ps1",
}


def sanitize_filename(filename: Optional[str], default_stem: str = "document") -> str:
    """Sanitizes an untrusted filename for safe storage and display.
    
    Strips directory traversal sequences, null bytes, and non-printable characters.
    """
    if not filename or not str(filename).strip():
        return f"{default_stem}.bin"

    # Strip any directory path components
    raw_name = str(filename).strip()
    # Remove null bytes immediately
    raw_name = raw_name.replace("\x00", "")
    # Normalize separators and take basename
    raw_name = os.path.basename(raw_name.replace("\\", "/"))

    # Extract stem and extension
    parsed = Path(raw_name)
    ext = parsed.suffix.lower()
    stem = parsed.stem

    # Remove unsafe characters from stem (keep only alphanumeric, dash, underscore, dot)
    clean_stem = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", stem)
    # Collapse multiple underscores
    clean_stem = re.sub(r"_+", "_", clean_stem).strip("._-")

    if not clean_stem:
        clean_stem = default_stem

    # Limit stem length to 100 characters to prevent buffer issues
    clean_stem = clean_stem[:100]

    return f"{clean_stem}{ext}"


def detect_file_format(content: bytes) -> Optional[str]:
    """Inspects leading magic bytes to identify actual binary format."""
    if not content:
        return None

    # Check PNG (8 bytes)
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    # Check JPEG (3 bytes)
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"

    # Check PDF (first 1024 bytes for standard %PDF- header)
    header_sample = content[:1024]
    if b"%PDF-" in header_sample:
        return "pdf"

    return None


def validate_document_upload(
    filename: Optional[str],
    declared_content_type: Optional[str],
    content: bytes,
    max_size_bytes: Optional[int] = None,
) -> Tuple[str, str, str, int]:
    """Strictly validates uploaded document payload for size, extension, MIME, and magic bytes.
    
    Args:
        filename: Original filename provided in upload.
        declared_content_type: Browser-supplied Content-Type header.
        content: Raw document binary bytes.
        max_size_bytes: Optional file size limit override.
        
    Returns:
        Tuple of (sanitized_filename, validated_mime_type, file_extension, file_size_bytes).
        
    Raises:
        DocumentValidationError: If any security, format, or size check fails.
    """
    effective_max_size = max_size_bytes or settings.MAX_DOCUMENT_FILE_SIZE_BYTES

    # 1. Reject empty file
    if not content or len(content) == 0:
        raise DocumentValidationError("Upload rejected: File is empty (0 bytes).")

    # 2. Reject oversized file
    file_size = len(content)
    if file_size > effective_max_size:
        max_mb = effective_max_size / (1024 * 1024)
        raise DocumentSizeExceededError(
            f"Upload rejected: File size ({file_size / (1024 * 1024):.2f} MB) "
            f"exceeds maximum allowed limit of {max_mb:.0f} MB."
        )

    # 3. Validate filename & extension
    if not filename or not str(filename).strip():
        raise DocumentValidationError("Upload rejected: Original filename is missing.")

    clean_filename = sanitize_filename(filename)
    ext = Path(clean_filename).suffix.lower()

    if not ext:
        raise DocumentValidationError("Upload rejected: File has no extension.")

    if ext in DISALLOWED_EXTENSIONS:
        raise DocumentValidationError(
            f"Upload rejected: File extension '{ext}' is forbidden for security reasons."
        )

    if ext not in ALLOWED_EXTENSIONS_MAP:
        raise DocumentValidationError(
            f"Upload rejected: Unsupported file extension '{ext}'. "
            "Supported formats are PDF (.pdf), PNG (.png), and JPEG (.jpg, .jpeg)."
        )

    expected_format_by_ext = ALLOWED_EXTENSIONS_MAP[ext]

    # 4. Validate binary magic bytes signature
    detected_format = detect_file_format(content)
    if not detected_format:
        raise DocumentValidationError(
            "Upload rejected: File content is corrupted or does not match a supported binary signature "
            "(expected valid PDF, PNG, or JPEG header)."
        )

    if detected_format != expected_format_by_ext:
        raise DocumentValidationError(
            f"Upload rejected: File content signature ({detected_format.upper()}) "
            f"does not match file extension '{ext}' ({expected_format_by_ext.upper()})."
        )

    # 5. Validate declared MIME type
    clean_mime = (declared_content_type or "").strip().lower()
    # Normalize MIME with charset if present (e.g. 'application/pdf; charset=binary')
    if ";" in clean_mime:
        clean_mime = clean_mime.split(";")[0].strip()

    canonical_mime = CANONICAL_MIME_TYPES[detected_format]

    # If browser supplied a MIME type, ensure it doesn't contradict the actual format
    if clean_mime and clean_mime not in ("application/octet-stream", "binary/octet-stream"):
        if clean_mime in ALLOWED_MIME_TYPES_MAP:
            expected_format_by_mime = ALLOWED_MIME_TYPES_MAP[clean_mime]
            if expected_format_by_mime != detected_format:
                raise DocumentValidationError(
                    f"Upload rejected: Declared MIME type '{clean_mime}' "
                    f"conflicts with actual file content ({detected_format.upper()})."
                )
        else:
            # Non-standard or disallowed MIME
            raise DocumentValidationError(
                f"Upload rejected: Unsupported declared MIME type '{clean_mime}'."
            )

    return clean_filename, canonical_mime, ext, file_size


async def read_upload_file_bounded(
    file: Any,
    max_size_bytes: Optional[int] = None,
    chunk_size: int = 64 * 1024,
) -> bytes:
    """Read an UploadFile stream in fixed chunks, stopping immediately if max_size_bytes is exceeded.

    Guarantees:
    - Bounded memory reading in fixed chunk_size increments (default 64 KB).
    - Stops reading and aborts immediately upon exceeding max_size_bytes without buffering remaining content.
    - Closes temporary upload file resources cleanly in all paths (success, error, cancellation).
    - Does not rely on Content-Length header as the only size check.
    """
    effective_max = max_size_bytes or settings.MAX_DOCUMENT_FILE_SIZE_BYTES
    buffer = bytearray()
    total_read = 0

    try:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > effective_max:
                max_mb = effective_max / (1024 * 1024)
                raise DocumentSizeExceededError(
                    f"Upload rejected: File size exceeds maximum allowed limit of {max_mb:.0f} MB."
                )
            buffer.extend(chunk)
    finally:
        try:
            await file.close()
        except Exception:
            pass

    return bytes(buffer)
