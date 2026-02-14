"""
Shared SQLite base class for consistent connection management.

Provides:
- Persistent connection with lazy initialization
- Thread-safe async lock for concurrent access
- WAL mode for better concurrency
- Clean connection lifecycle management
"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Optional


class SQLiteStore:
    """Base class for SQLite-backed stores with consistent connection management."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser()
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()

    def _db(self) -> sqlite3.Connection:
        """Get or create persistent database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def close(self):
        """Explicitly close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
