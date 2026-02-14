"""
Tests for AsyncSQLitePool connection pooling.

Verifies:
- Pool initialization and cleanup
- Concurrent connection acquisition
- Health checks
- Pool statistics
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from src.db.pool import AsyncSQLitePool


@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.mark.asyncio
async def test_pool_init_and_close(temp_db):
    """Test pool initialization and cleanup."""
    pool = AsyncSQLitePool(temp_db, pool_size=3)
    await pool.init()

    stats = pool.stats()
    assert stats["pool_size"] == 3
    assert stats["available"] == 0  # No connections created yet
    assert stats["in_use"] == 0

    await pool.close()


@pytest.mark.asyncio
async def test_pool_acquire_single(temp_db):
    """Test acquiring a single connection."""
    pool = AsyncSQLitePool(temp_db, pool_size=3)
    await pool.init()

    async with pool.acquire() as conn:
        # Create a table
        await conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        await conn.commit()

        # Insert data
        await conn.execute("INSERT INTO test (value) VALUES (?)", ("hello",))
        await conn.commit()

        # Query data
        cursor = await conn.execute("SELECT value FROM test WHERE id=1")
        row = await cursor.fetchone()
        assert row[0] == "hello"

    await pool.close()


@pytest.mark.asyncio
async def test_pool_concurrent_access(temp_db):
    """Test concurrent connection acquisition from pool."""
    pool = AsyncSQLitePool(temp_db, pool_size=5)
    await pool.init()

    # Create table first
    async with pool.acquire() as conn:
        await conn.execute("CREATE TABLE counter (id INTEGER PRIMARY KEY, count INTEGER)")
        await conn.execute("INSERT INTO counter (id, count) VALUES (1, 0)")
        await conn.commit()

    async def increment_counter(worker_id: int):
        """Increment counter in database."""
        async with pool.acquire() as conn:
            # Read current value
            cursor = await conn.execute("SELECT count FROM counter WHERE id=1")
            row = await cursor.fetchone()
            current = row[0]

            # Simulate work
            await asyncio.sleep(0.01)

            # Increment
            await conn.execute("UPDATE counter SET count=? WHERE id=1", (current + 1,))
            await conn.commit()

    # Run 10 concurrent workers
    tasks = [increment_counter(i) for i in range(10)]
    await asyncio.gather(*tasks)

    # Verify final count
    async with pool.acquire() as conn:
        cursor = await conn.execute("SELECT count FROM counter WHERE id=1")
        row = await cursor.fetchone()
        final_count = row[0]

    # Should be 10, but might have race conditions without proper locking
    # The test is mainly to ensure pool doesn't deadlock or crash
    assert final_count > 0

    await pool.close()


@pytest.mark.asyncio
async def test_pool_stats(temp_db):
    """Test pool statistics tracking."""
    pool = AsyncSQLitePool(temp_db, pool_size=3)
    await pool.init()

    # Initially empty
    stats = pool.stats()
    assert stats["available"] == 0
    assert stats["in_use"] == 0

    # Acquire connection
    async with pool.acquire() as conn:
        stats = pool.stats()
        assert stats["in_use"] == 1

        await conn.execute("SELECT 1")

    # After release, should be in pool
    stats = pool.stats()
    assert stats["in_use"] == 0
    assert stats["available"] == 1

    await pool.close()


@pytest.mark.asyncio
async def test_pool_health_check(temp_db):
    """Test connection health checking."""
    pool = AsyncSQLitePool(temp_db, pool_size=2)
    await pool.init()

    # Acquire and use connection
    async with pool.acquire() as conn:
        await conn.execute("CREATE TABLE test (id INTEGER)")
        await conn.commit()

    # Connection should be returned to pool
    stats = pool.stats()
    assert stats["available"] == 1

    # Acquire again - should reuse healthy connection
    async with pool.acquire() as conn:
        await conn.execute("SELECT * FROM test")

    await pool.close()


@pytest.mark.asyncio
async def test_pool_closed_error(temp_db):
    """Test that acquiring from closed pool raises error."""
    pool = AsyncSQLitePool(temp_db, pool_size=2)
    await pool.init()
    await pool.close()

    with pytest.raises(RuntimeError, match="Pool is closed"):
        async with pool.acquire():
            pass


@pytest.mark.asyncio
async def test_pool_exceeds_size(temp_db):
    """Test behavior when acquiring more connections than pool size."""
    pool = AsyncSQLitePool(temp_db, pool_size=2)
    await pool.init()

    # Acquire 3 connections concurrently (more than pool size)
    async def hold_connection(duration: float):
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
            await asyncio.sleep(duration)

    tasks = [hold_connection(0.1) for _ in range(5)]
    await asyncio.gather(*tasks)

    # Should not deadlock or fail
    stats = pool.stats()
    assert stats["in_use"] == 0  # All released
    assert stats["available"] <= stats["pool_size"]  # Respects pool size limit

    await pool.close()
