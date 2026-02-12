"""Tests for observability metrics module."""

import pytest

from src.memory.store import memory
from src.observability.metrics import get_agent_performance, get_daily_summary, get_health_snapshot


@pytest.fixture(autouse=True)
def init_memory(tmp_path):
    """Observability reads from the global memory singleton."""
    memory.db_path = str(tmp_path / "test_obs.db")
    memory.init()
    yield
    memory._conn = None


class TestDailySummary:
    def test_returns_list(self):
        result = get_daily_summary(days=3)
        assert isinstance(result, list)
        assert len(result) == 3

    def test_each_day_has_required_fields(self):
        result = get_daily_summary(days=1)
        day = result[0]
        assert "date" in day
        assert "tasks_completed" in day
        assert "defects_filed" in day
        assert "errors" in day
        assert "events_total" in day

    def test_default_days(self):
        result = get_daily_summary()
        assert len(result) == 7


class TestAgentPerformance:
    def test_returns_list(self):
        result = get_agent_performance()
        assert isinstance(result, list)

    def test_agent_entries_have_fields(self):
        result = get_agent_performance()
        if result:
            agent = result[0]
            assert "id" in agent
            assert "name" in agent
            assert "status" in agent


class TestHealthSnapshot:
    def test_returns_dict(self):
        result = get_health_snapshot()
        assert isinstance(result, dict)
        assert "monitor" in result
        assert "circuits" in result
        assert "escalation" in result
        assert "dead_letter_depth" in result

    def test_monitor_has_status(self):
        result = get_health_snapshot()
        monitor = result["monitor"]
        assert "running" in monitor
        assert "uptime_seconds" in monitor
