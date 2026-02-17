"""
Connection pooling for high-concurrency SQLite databases.

Provides async connection pooling to prevent lock contention when multiple
coroutines access the same database. Used by memory.db and ml.db.

Design:
- Pool size configurable (default 5 connections)
- Lazy connection creation (only create when needed)
- Health checks on checkout (detect stale connections)
- Graceful cleanup on pool shutdown
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from src.db.sqlite_store import aconnect_encrypted

logger = logging.getLogger("nexus.db.pool")


class AsyncSQLitePool:
    """Async connection pool for SQLite databases.

    Manages a pool of aiosqlite connections to reduce lock contention
    under parallel execution. Each connection is lazily created and
    health-checked on checkout.

    Usage:
        pool = AsyncSQLitePool(db_path="~/.nexus/memory.db", pool_size=5)
        await pool.init()

        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO ...")
            await conn.commit()

        await pool.close()
    """

    def __init__(self, db_path: str | Path, pool_size: int = 5):
        """Initialize pool (connections created lazily on first acquire).

        Args:
            db_path: Path to SQLite database file.
            pool_size: Maximum number of connections to maintain.
        """
        self.db_path = Path(db_path).expanduser()
        self.pool_size = pool_size
        self._pool: list[aiosqlite.Connection] = []
        self._in_use: set[aiosqlite.Connection] = set()
        self._lock = asyncio.Lock()
        self._closed = False

    async def init(self):
        """Initialize the pool (currently a no-op, connections created on demand)."""
        logger.info(f"Initialized connection pool for {self.db_path} (size={self.pool_size})")

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new encrypted connection with standard pragmas."""
        async with aconnect_encrypted(str(self.db_path)) as _db:
            # aconnect_encrypted returns an already-open connection
            # We need to return it without closing, so we'll create manually
            pass

        # Create connection manually to avoid auto-close
        conn = await aiosqlite.connect(str(self.db_path))

        # Apply encryption PRAGMAs
        try:
            from src.db.encryption import get_db_encryption_key, is_encryption_available
            if is_encryption_available():
                key = get_db_encryption_key()
                await conn.execute(f"PRAGMA key = \"x'{key}'\"")  # noqa: S608
                await conn.execute("PRAGMA cipher_page_size = 4096")
                await conn.execute("PRAGMA kdf_iter = 256000")
        except Exception:
            logger.debug("Encryption not applied to pooled connection")

        # Standard PRAGMAs
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")

        return conn

    async def _health_check(self, conn: aiosqlite.Connection) -> bool:
        """Check if connection is healthy.

        Returns:
            True if connection is usable, False if it should be discarded.
        """
        try:
            await conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning(f"Connection health check failed: {e}")
            return False

    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool.

        Yields a connection that is automatically returned to the pool
        when the context exits. Connection is health-checked before use.

        Yields:
            aiosqlite.Connection ready for queries.

        Raises:
            RuntimeError: If pool is closed.
        """
        if self._closed:
            raise RuntimeError("Pool is closed")

        conn: aiosqlite.Connection | None = None

        async with self._lock:
            # Try to get connection from pool
            while self._pool:
                candidate = self._pool.pop()
                if await self._health_check(candidate):
                    conn = candidate
                    break
                else:
                    # Stale connection, close it
                    try:
                        await candidate.close()
                    except Exception:
                        pass

            # Create new connection if needed
            if conn is None:
                conn = await self._create_connection()

            self._in_use.add(conn)

        try:
            yield conn
        finally:
            async with self._lock:
                self._in_use.discard(conn)

                # Return to pool if under limit, otherwise close
                if len(self._pool) < self.pool_size and not self._closed:
                    self._pool.append(conn)
                else:
                    try:
                        await conn.close()
                    except Exception:
                        pass

    async def close(self):
        """Close all connections in the pool."""
        async with self._lock:
            self._closed = True

            # Close pooled connections
            for conn in self._pool:
                try:
                    await conn.close()
                except Exception as e:
                    logger.debug(f"Error closing pooled connection: {e}")

            self._pool.clear()

            # Close in-use connections (they'll be cleaned up when released)
            for conn in list(self._in_use):
                try:
                    await conn.close()
                except Exception as e:
                    logger.debug(f"Error closing in-use connection: {e}")

            self._in_use.clear()

        logger.info(f"Closed connection pool for {self.db_path}")

    def stats(self) -> dict:
        """Get pool statistics.

        Returns:
            Dict with available, in_use, and pool_size counts.
        """
        return {
            "available": len(self._pool),
            "in_use": len(self._in_use),
            "pool_size": self.pool_size,
            "db_path": str(self.db_path),
        }
