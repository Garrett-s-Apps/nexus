"""Tests for CLI Session Pool."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.sessions.cli_pool import CLISession, CLISessionPool


class TestCLISession:
    def test_initial_state(self):
        session = CLISession("thread-1", "/tmp/project")
        assert session.thread_ts == "thread-1"
        assert session.process is None
        assert not session.alive

    def test_is_idle_when_expired(self):
        session = CLISession("thread-1", "/tmp/project")
        session.last_used = time.monotonic() - 2000
        assert session.is_idle

    def test_not_idle_when_fresh(self):
        session = CLISession("thread-1", "/tmp/project")
        assert not session.is_idle

    @pytest.mark.asyncio
    async def test_start_fails_without_claude_cli(self):
        session = CLISession("thread-1", "/tmp/project")
        with patch("src.sessions.cli_pool.shutil.which", return_value=None):
            result = await session.start()
            assert result is False

    @pytest.mark.asyncio
    async def test_kill_no_process(self):
        session = CLISession("thread-1", "/tmp/project")
        await session.kill()  # should not raise


class TestCLISessionPool:
    def test_initial_state(self):
        pool = CLISessionPool()
        assert pool.active_count() == 0

    def test_status(self):
        pool = CLISessionPool()
        status = pool.status()
        assert status["active_sessions"] == 0
        assert status["total_created"] == 0
        assert status["sessions"] == []

    @pytest.mark.asyncio
    async def test_cleanup_stale_removes_idle(self):
        pool = CLISessionPool()
        session = CLISession("thread-1", "/tmp")
        session.last_used = time.monotonic() - 2000
        session.process = MagicMock()
        session.process.returncode = None
        session.process.terminate = MagicMock()
        session.process.wait = AsyncMock()
        session.process.kill = MagicMock()
        pool._sessions["thread-1"] = session
        await pool.cleanup_stale()
        assert "thread-1" not in pool._sessions

    @pytest.mark.asyncio
    async def test_shutdown_clears_all(self):
        pool = CLISessionPool()
        session = CLISession("thread-1", "/tmp")
        session.process = MagicMock()
        session.process.returncode = None
        session.process.terminate = MagicMock()
        session.process.wait = AsyncMock()
        session.process.kill = MagicMock()
        pool._sessions["thread-1"] = session
        await pool.shutdown()
        assert len(pool._sessions) == 0
