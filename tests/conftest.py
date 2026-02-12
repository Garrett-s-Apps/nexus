"""Shared test fixtures for NEXUS test suite."""

import os
import sys
import json
import sqlite3
import asyncio
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub out proprietary SDK that isn't pip-installable
if "claude_agent_sdk" not in sys.modules:
    _stub = types.ModuleType("claude_agent_sdk")
    _stub.ClaudeAgentOptions = MagicMock
    _stub.query = MagicMock
    sys.modules["claude_agent_sdk"] = _stub


@pytest.fixture
def memory_db(tmp_path):
    """Fresh in-memory SQLite database for testing."""
    db_path = str(tmp_path / "test_memory.db")
    from src.memory.store import Memory
    mem = Memory()
    mem.db_path = db_path
    mem.init()
    return mem


@pytest.fixture
def cost_db(tmp_path):
    """Fresh cost tracker with temp database."""
    db_path = str(tmp_path / "test_cost.db")
    from src.cost.tracker import CostTracker
    tracker = CostTracker(db_path=db_path)
    return tracker


@pytest.fixture
def mock_slack_client():
    """Mock Slack AsyncWebClient."""
    client = AsyncMock()
    client.chat_postMessage = AsyncMock(return_value={"ok": True})
    client.files_upload_v2 = AsyncMock(return_value={"ok": True})
    client.conversations_list = AsyncMock(return_value={
        "channels": [{"name": "garrett-nexus", "id": "C123456"}]
    })
    client.auth_test = AsyncMock(return_value={"user_id": "U_BOT"})
    return client


@pytest.fixture
def mock_allm_call():
    """Mock the allm_call function to return canned LLM responses."""
    async def _mock_call(prompt, model, max_tokens=4096, system=""):
        return '{"intent": "chat", "summary": "test", "response": "OK"}', 0.001
    with patch("src.agents.base.allm_call", side_effect=_mock_call) as m:
        yield m


@pytest.fixture
def sample_directive():
    """Sample directive data."""
    return {
        "id": "dir-test001",
        "text": "Build a REST API with user authentication",
        "status": "received",
        "intent": "new_directive",
        "project_path": "/tmp/test-project",
    }


@pytest.fixture
def sample_tasks():
    """Sample task board tasks."""
    return [
        {"id": "dir-test001-task-1", "title": "Create user model", "description": "SQLAlchemy user model", "priority": 10, "depends_on": []},
        {"id": "dir-test001-task-2", "title": "Create auth endpoints", "description": "Login/register API", "priority": 8, "depends_on": ["dir-test001-task-1"]},
        {"id": "dir-test001-task-3", "title": "Add JWT middleware", "description": "Token verification", "priority": 7, "depends_on": ["dir-test001-task-1"]},
    ]
