#!/usr/bin/env python3
"""
Migrate existing plaintext SQLite databases to SQLCipher encrypted format.

This script:
1. Checks that NEXUS_MASTER_SECRET is set
2. For each database, creates an encrypted copy using sqlcipher_export
3. Backs up the original and replaces it with the encrypted version

Usage:
    NEXUS_MASTER_SECRET=your-secret python scripts/migrate_encrypt_dbs.py

Requirements:
    - pysqlcipher3 must be installed
    - NEXUS_MASTER_SECRET must be set
    - All NEXUS services must be stopped during migration
"""

import os
import shutil
import sqlite3
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import NEXUS_DIR
from src.db.encryption import get_db_encryption_key, is_encryption_available

# All NEXUS databases to migrate
DATABASES = [
    ("memory.db", "Conversation history, PII"),
    ("cost.db", "API usage tracking"),
    ("kpi.db", "KPI metrics"),
    ("registry.db", "Agent configurations"),
    ("ml.db", "ML embeddings, outcomes"),
    ("knowledge.db", "RAG knowledge chunks"),
    ("sessions.db", "Session state"),
]


def is_already_encrypted(db_path: str) -> bool:
    """Check if a database is already encrypted (unreadable by plain sqlite3)."""
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.close()
        return False  # Readable = not encrypted
    except Exception:
        return True  # Unreadable = likely encrypted


def migrate_database(db_path: str, description: str, encryption_key: str) -> bool:
    """Migrate a single database from plaintext to encrypted.

    Uses the SQLCipher ATTACH + sqlcipher_export pattern:
    1. Open the plaintext DB with plain sqlite3
    2. Open a new encrypted DB with sqlcipher
    3. Export all data from plaintext to encrypted
    4. Replace the original with the encrypted version

    Returns True on success, False on failure.
    """
    if not os.path.exists(db_path):
        print(f"  SKIP: {db_path} does not exist")
        return True

    if is_already_encrypted(db_path):
        print(f"  SKIP: {db_path} is already encrypted")
        return True

    backup_path = f"{db_path}.backup.{int(time.time())}"
    encrypted_path = f"{db_path}.encrypted"

    try:
        # Import sqlcipher
        from pysqlcipher3 import dbapi2 as sqlcipher  # type: ignore[import-untyped]

        # Step 1: Create encrypted database
        enc_conn = sqlcipher.connect(encrypted_path)
        enc_conn.execute(f"PRAGMA key = \"x'{encryption_key}'\"")  # noqa: S608
        enc_conn.execute("PRAGMA cipher_page_size = 4096")
        enc_conn.execute("PRAGMA kdf_iter = 256000")

        # Step 2: Attach plaintext database and copy data
        enc_conn.execute(f"ATTACH DATABASE '{db_path}' AS plaintext KEY ''")  # noqa: S608
        enc_conn.execute("SELECT sqlcipher_export('main', 'plaintext')")
        enc_conn.execute("DETACH DATABASE plaintext")
        enc_conn.execute("PRAGMA journal_mode=WAL")
        enc_conn.execute("PRAGMA busy_timeout=5000")
        enc_conn.commit()
        enc_conn.close()

        # Step 3: Verify encrypted database is readable with key
        verify_conn = sqlcipher.connect(encrypted_path)
        verify_conn.execute(f"PRAGMA key = \"x'{encryption_key}'\"")  # noqa: S608
        verify_conn.execute("PRAGMA cipher_page_size = 4096")
        verify_conn.execute("PRAGMA kdf_iter = 256000")
        tables = verify_conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        verify_conn.close()

        if tables == 0:
            print(f"  ERROR: Encrypted {db_path} has no tables — aborting")
            os.remove(encrypted_path)
            return False

        # Step 4: Backup original and replace
        shutil.copy2(db_path, backup_path)
        os.replace(encrypted_path, db_path)

        # Clean up WAL/SHM files from old plaintext DB
        for suffix in ["-wal", "-shm"]:
            wal_path = f"{db_path}{suffix}"
            if os.path.exists(wal_path):
                os.remove(wal_path)

        print(f"  OK: {db_path} ({description})")
        print(f"      Backup: {backup_path}")
        print(f"      Tables: {tables}")
        return True

    except ImportError:
        print("  ERROR: pysqlcipher3 is not installed")
        print("         Install with: pip install pysqlcipher3")
        return False
    except Exception as e:
        print(f"  ERROR migrating {db_path}: {e}")
        # Clean up partial encrypted file
        if os.path.exists(encrypted_path):
            os.remove(encrypted_path)
        return False


def main():
    print("NEXUS Database Encryption Migration")
    print("=" * 55)
    print()

    # Verify prerequisites
    if not is_encryption_available():
        print("ERROR: NEXUS_MASTER_SECRET is not set.")
        print("Set it in your environment or in ~/.nexus/.env.keys")
        print()
        print("Example:")
        print("  export NEXUS_MASTER_SECRET='your-strong-secret-here'")
        sys.exit(1)

    try:
        from pysqlcipher3 import dbapi2  # type: ignore[import-untyped] # noqa: F401
    except ImportError:
        print("ERROR: pysqlcipher3 is not installed.")
        print("Install with: pip install pysqlcipher3")
        sys.exit(1)

    encryption_key = get_db_encryption_key()
    print(f"Encryption key derived (salt: ~/.nexus/.db_salt)")
    print(f"NEXUS directory: {NEXUS_DIR}")
    print()

    # Migrate each database
    success_count = 0
    fail_count = 0

    for db_name, description in DATABASES:
        db_path = os.path.join(NEXUS_DIR, db_name)
        print(f"Migrating {db_name} ({description})...")

        if migrate_database(db_path, description, encryption_key):
            success_count += 1
        else:
            fail_count += 1

    print()
    print(f"Migration complete: {success_count} succeeded, {fail_count} failed")

    if fail_count > 0:
        print()
        print("WARNING: Some databases failed to migrate.")
        print("Check the errors above and retry after fixing issues.")
        print("Backup files are preserved with .backup.TIMESTAMP extension.")
        sys.exit(1)

    print()
    print("All databases encrypted successfully.")
    print("Backup files preserved with .backup.TIMESTAMP extension.")
    print("You can remove backups after verifying the system works correctly.")


if __name__ == "__main__":
    main()
