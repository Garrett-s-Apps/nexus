"""
Bridge between NEXUS CostTracker and costwise analytics backend.

costwise becomes the source of truth for detailed cost data:
- Per-call records with provider, model, tokens, latency, tags
- Optimization analysis (model downgrades, cache, error rate, prompt bloat)
- Time-series analytics (daily costs, model breakdowns)

NEXUS CostTracker remains the budget enforcement layer:
- Session/hourly/monthly caps
- Model downgrades when over budget
- CFO alerts and escalation

Every NEXUS cost event is dual-written to costwise with rich metadata
(agent name, project, session_id, org layer).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.config import NEXUS_DIR

logger = logging.getLogger("nexus.cost.costwise")

# Store costwise DB alongside other NEXUS databases
COSTWISE_DB_PATH = os.path.join(NEXUS_DIR, "costwise.db")

# Map NEXUS model short names to costwise-compatible provider+model
_NEXUS_MODEL_MAP: dict[str, tuple[str, str]] = {
    "opus": ("anthropic", "claude-opus-4-20250514"),
    "sonnet": ("anthropic", "claude-sonnet-4-20250514"),
    "haiku": ("anthropic", "claude-3-5-haiku-20241022"),
    "gemini-2.0-flash": ("google", "gemini-2.0-flash"),
    "gemini-2.5-pro": ("google", "gemini-2.5-pro"),
    "o3": ("openai", "o3"),
    "gpt-4o": ("openai", "gpt-4o"),
    # Claude Code CLI sessions (Max subscription, $0 cost)
    "claude-code:opus": ("anthropic", "claude-code:opus"),
    "claude-code:sonnet": ("anthropic", "claude-code:sonnet"),
    "claude-code:haiku": ("anthropic", "claude-code:haiku"),
}

# Flag: is costwise package available?
_COSTWISE_AVAILABLE = False
try:
    import costwise  # noqa: F401
    _COSTWISE_AVAILABLE = True
except ImportError:
    logger.info("costwise package not installed — analytics features disabled")


def _get_costwise_tracker():
    """Get or create the costwise tracker singleton pointed at NEXUS DB."""
    from costwise.tracker import get_tracker
    return get_tracker(
        db_path=COSTWISE_DB_PATH,
        tags={"org": "nexus", "env": os.environ.get("NEXUS_ENV", "production")},
    )


def record_cost(
    model: str,
    agent_name: str,
    tokens_in: int,
    tokens_out: int,
    project: str = "",
    session_id: str = "",
    cached_tokens: int = 0,
    latency_ms: float = 0.0,
    success: bool = True,
    error: str = "",
) -> None:
    """Record a cost event in costwise (called from NEXUS CostTracker)."""
    if not _COSTWISE_AVAILABLE:
        return
    try:
        tracker = _get_costwise_tracker()
        provider, cw_model = _NEXUS_MODEL_MAP.get(model, ("unknown", model))

        tags: dict[str, str] = {"agent": agent_name}
        if project:
            tags["project"] = project

        metadata: dict[str, Any] = {}
        if session_id:
            metadata["session_id"] = session_id

        tracker.record(
            provider=provider,
            model=cw_model,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cached_tokens=cached_tokens,
            latency_ms=latency_ms,
            success=success,
            error=error[:200] if error else "",
            tags=tags,
            metadata=metadata,
        )
    except Exception as e:
        logger.warning("costwise record failed (non-fatal): %s", e)


def get_summary(period: str = "30d", days: int | None = None) -> dict[str, Any]:
    """Get costwise summary as a dict (safe for JSON serialization)."""
    if not _COSTWISE_AVAILABLE:
        return {"error": "costwise not installed"}
    tracker = _get_costwise_tracker()
    summary = tracker.summary(period=period, days=days)
    return {
        "period": summary.period,
        "total_cost": summary.total_cost,
        "total_requests": summary.total_requests,
        "total_input_tokens": summary.total_input_tokens,
        "total_output_tokens": summary.total_output_tokens,
        "avg_cost_per_request": summary.avg_cost_per_request,
        "avg_latency_ms": summary.avg_latency_ms,
        "error_rate": summary.error_rate,
        "by_model": summary.by_model,
        "by_provider": summary.by_provider,
        "by_tag": summary.by_tag,
    }


def get_daily_costs(days: int = 30) -> list[dict[str, Any]]:
    """Get daily cost time series."""
    if not _COSTWISE_AVAILABLE:
        return []
    result: list[dict[str, Any]] = _get_costwise_tracker().daily_costs(days)
    return result


def get_model_breakdown(days: int = 30) -> list[dict[str, Any]]:
    """Get cost breakdown by model."""
    if not _COSTWISE_AVAILABLE:
        return []
    result: list[dict[str, Any]] = _get_costwise_tracker().model_breakdown(days)
    return result


def get_optimization_tips(days: int = 30) -> list[dict[str, Any]]:
    """Get optimization recommendations from the costwise analyzer."""
    if not _COSTWISE_AVAILABLE:
        return []
    from dataclasses import asdict

    from costwise.analyzer import analyze
    tracker = _get_costwise_tracker()
    tips = analyze(tracker.storage, days)
    return [asdict(tip) for tip in tips]


def get_agent_costs(agent_name: str, days: int = 30) -> dict[str, Any]:
    """Get cost data for a specific agent (for cost_consultant queries)."""
    if not _COSTWISE_AVAILABLE:
        return {"agent": agent_name, "total_cost": 0.0, "calls": 0}
    tracker = _get_costwise_tracker()
    records = tracker.query(tag_key="agent", tag_value=agent_name)
    if not records:
        return {"agent": agent_name, "total_cost": 0.0, "calls": 0}

    import time
    cutoff = time.time() - (days * 86400)
    recent = [r for r in records if r.timestamp >= cutoff]

    total_cost = sum(r.total_cost for r in recent)
    by_model: dict[str, float] = {}
    for r in recent:
        by_model[r.model] = by_model.get(r.model, 0.0) + r.total_cost

    return {
        "agent": agent_name,
        "total_cost": round(total_cost, 4),
        "calls": len(recent),
        "by_model": by_model,
        "avg_cost_per_call": round(total_cost / len(recent), 6) if recent else 0.0,
        "error_rate": sum(1 for r in recent if not r.success) / len(recent) if recent else 0.0,
    }


def get_project_costs(project: str, days: int = 30) -> dict[str, Any]:
    """Get cost data for a specific project."""
    if not _COSTWISE_AVAILABLE:
        return {"project": project, "total_cost": 0.0, "calls": 0}
    tracker = _get_costwise_tracker()
    records = tracker.query(tag_key="project", tag_value=project)
    if not records:
        return {"project": project, "total_cost": 0.0, "calls": 0}

    import time
    cutoff = time.time() - (days * 86400)
    recent = [r for r in records if r.timestamp >= cutoff]

    total_cost = sum(r.total_cost for r in recent)
    return {
        "project": project,
        "total_cost": round(total_cost, 4),
        "calls": len(recent),
    }


def register_nexus_pricing() -> None:
    """Register NEXUS-specific pricing (Claude Code at $0 for Max sub)."""
    if not _COSTWISE_AVAILABLE:
        return
    from costwise.pricing import set_price as costwise_set_price
    costwise_set_price("claude-code:opus", 0.0, 0.0)
    costwise_set_price("claude-code:sonnet", 0.0, 0.0)
    costwise_set_price("claude-code:haiku", 0.0, 0.0)


def healthcheck() -> dict[str, Any]:
    """Check costwise backend health."""
    if not _COSTWISE_AVAILABLE:
        return {"status": "unavailable", "error": "costwise package not installed"}
    try:
        tracker = _get_costwise_tracker()
        summary = tracker.summary(days=1)
        return {
            "status": "up",
            "db_path": COSTWISE_DB_PATH,
            "db_exists": os.path.exists(COSTWISE_DB_PATH),
            "records_24h": summary.total_requests,
        }
    except Exception as e:
        return {"status": "down", "error": str(e)}


def get_bloat_report() -> dict[str, Any]:
    """Get model bloat detection report."""
    from src.cost.bloat_detector import bloat_detector
    return bloat_detector.get_bloat_summary()


def get_efficiency_report(days: int = 30) -> dict[str, Any]:
    """Get cost efficiency metrics."""
    from src.cost.bloat_detector import bloat_detector
    return bloat_detector.get_efficiency_report(days)


def export_costs(days: int = 30, fmt: str = "json") -> str:
    """Export cost records as JSON or CSV."""
    if not _COSTWISE_AVAILABLE:
        return "[]" if fmt == "json" else ""
    import json as json_mod
    import time as time_mod

    tracker = _get_costwise_tracker()
    cutoff = time_mod.time() - (days * 86400)
    records = tracker.storage.query(since=cutoff)

    rows = []
    for r in records:
        rows.append({
            "timestamp": r.timestamp,
            "provider": r.provider,
            "model": r.model,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cached_tokens": r.cached_tokens,
            "total_cost": r.total_cost,
            "success": r.success,
            "latency_ms": r.latency_ms,
            "tags": r.tags if hasattr(r, "tags") else {},
        })

    if fmt == "csv":
        if not rows:
            return "timestamp,provider,model,input_tokens,output_tokens,cached_tokens,total_cost,success,latency_ms\n"
        header = ",".join(rows[0].keys())
        lines = [header]
        for row in rows:
            vals = []
            for v in row.values():
                if isinstance(v, dict):
                    vals.append(f'"{v}"')
                else:
                    vals.append(str(v))
            lines.append(",".join(vals))
        return "\n".join(lines)

    return json_mod.dumps(rows, default=str)


# Register $0 pricing for Claude Code CLI models at import time
register_nexus_pricing()
