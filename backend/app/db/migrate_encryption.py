"""CLI entry point to migrate legacy unencrypted bank account numbers to versioned ciphertext."""

import sys
from app.db.session import SessionLocal
from app.core.security import migrate_legacy_vendor_accounts
from app.core.logging import logger


def main():
    logger.info("Starting legacy vendor account encryption migration...")
    with SessionLocal() as db:
        try:
            count = migrate_legacy_vendor_accounts(db)
            logger.info(f"Migration completed successfully. Migrated {count} records.")
        except Exception as e:
            logger.critical(f"Migration failed: {type(e).__name__}")
            sys.exit(1)


if __name__ == "__main__":
    main()
