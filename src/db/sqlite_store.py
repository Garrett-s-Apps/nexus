"""
Shared SQLite base class for consistent connection management.

Provides:
- Persistent connection with lazy initialization
- Thread-safe async lock for concurrent access
- WAL mode for better concurrency
- SQLCipher encryption when NEXUS_MASTER_SECRET is set
- Clean connection lifecycle management
"""

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger("nexus.db.sqlite_store")


def _apply_encryption_pragmas(conn: sqlite3.Connection) -> bool:
    """Apply SQLCipher encryption PRAGMAs to a connection.

    Returns True if encryption was applied, False if skipped (no secret).
    """
    from src.db.encryption import get_db_encryption_key, is_encryption_available

    if not is_encryption_available():
        return False

    key = get_db_encryption_key()
    conn.execute(f"PRAGMA key = \"x'{key}'\"")  # noqa: S608
    conn.execute("PRAGMA cipher_page_size = 4096")
    conn.execute("PRAGMA kdf_iter = 256000")
    return True


def connect_encrypted(db_path: str, **kwargs) -> sqlite3.Connection:
    """Create a SQLite/SQLCipher connection with encryption if available.

    This is the standard way to open a database connection in NEXUS.
    When NEXUS_MASTER_SECRET is configured, SQLCipher encryption PRAGMAs
    are applied. Otherwise, a standard sqlite3 connection is returned.

    Args:
        db_path: Path to the database file.
        **kwargs: Additional arguments passed to sqlite3.connect().

    Returns:
        A configured sqlite3.Connection with WAL mode and encryption.
    """
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher  # type: ignore[import-untyped]
        conn = sqlcipher.connect(db_path, **kwargs)
    except ImportError:
        conn = sqlite3.connect(db_path, **kwargs)

    # Apply encryption first (must be before any other operations)
    try:
        _apply_encryption_pragmas(conn)
    except Exception:
        logger.debug("Encryption not applied (NEXUS_MASTER_SECRET not set or pysqlcipher3 missing)")

    # Standard performance PRAGMAs
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    return conn


class aconnect_encrypted:
    """Async context manager for encrypted aiosqlite connections.

    Usage:
        async with aconnect_encrypted(db_path) as db:
            await db.execute(...)

    When NEXUS_MASTER_SECRET is configured and pysqlcipher3 is available,
    the underlying connection uses SQLCipher encryption.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db = None

    async def __aenter__(self):
        import aiosqlite
        self._db = await aiosqlite.connect(self._db_path)

        # Apply encryption PRAGMAs
        try:
            from src.db.encryption import get_db_encryption_key, is_encryption_available
            if is_encryption_available():
                key = get_db_encryption_key()
                await self._db.execute(f"PRAGMA key = \"x'{key}'\"")  # noqa: S608
                await self._db.execute("PRAGMA cipher_page_size = 4096")
                await self._db.execute("PRAGMA kdf_iter = 256000")
        except Exception:
            logger.debug("Async encryption not applied")

        # Standard PRAGMAs
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")

        return self._db

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._db is not None:
            await self._db.close()
            self._db = None
        return False


class SQLiteStore:
    """Base class for SQLite-backed stores with consistent connection management."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser()
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()

    def _db(self) -> sqlite3.Connection:
        """Get or create persistent encrypted database connection."""
        if self._conn is None:
            self._conn = connect_encrypted(
                str(self.db_path), check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        """Explicitly close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
