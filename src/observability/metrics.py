"""Metrics aggregation from KPI, cost, memory, and resilience stores."""

import logging
from datetime import datetime, timedelta

from src.memory.store import memory
from src.resilience.circuit_breaker import breaker_registry
from src.resilience.escalation import escalation_chain
from src.resilience.health_monitor import health_monitor

logger = logging.getLogger(__name__)


def get_daily_summary(days: int = 7) -> list[dict]:
    """Aggregate daily metrics over the given window."""
    summaries = []
    today = datetime.now().date()

    for offset in range(days):
        day = today - timedelta(days=offset)
        day_str = day.isoformat()

        events = memory.get_events_for_day(day_str) if hasattr(memory, "get_events_for_day") else []
        tasks_completed = sum(1 for e in events if e.get("event_type") == "task_completed")
        defects_filed = sum(1 for e in events if e.get("event_type") == "defect_filed")
        errors = sum(1 for e in events if e.get("event_type") == "agent_error")

        summaries.append({
            "date": day_str,
            "tasks_completed": tasks_completed,
            "defects_filed": defects_filed,
            "errors": errors,
            "events_total": len(events),
        })

    return list(reversed(summaries))


def get_agent_performance(days: int = 7) -> list[dict]:
    """Per-agent performance metrics."""
    agents = memory.get_all_agents()
    performance = []

    for agent in agents:
        performance.append({
            "id": agent.get("agent_id", agent.get("name", "unknown")),
            "name": agent.get("name", "unknown"),
            "status": agent.get("status", "idle"),
            "tasks_completed": agent.get("tasks_completed", 0),
            "last_action": agent.get("last_action", ""),
        })

    return sorted(performance, key=lambda a: a["tasks_completed"], reverse=True)


def get_health_snapshot() -> dict:
    """Combined health status from all resilience components."""
    return {
        "monitor": health_monitor.status(),
        "circuits": breaker_registry.all_statuses(),
        "escalation": escalation_chain.status(),
        "dead_letter_depth": escalation_chain.dead_letter_depth(),
    }
