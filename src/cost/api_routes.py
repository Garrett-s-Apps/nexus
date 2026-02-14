"""FastAPI routes for costwise analytics endpoints.

Exposes the full costwise API through the NEXUS server:
- Summary, daily costs, model breakdown
- Optimization tips from the analyzer
- Per-agent and per-project cost queries
- Health check for the costwise backend
"""

from fastapi import APIRouter

from src.cost.costwise_bridge import (
    export_costs,
    get_agent_costs,
    get_bloat_report,
    get_daily_costs,
    get_efficiency_report,
    get_model_breakdown,
    get_optimization_tips,
    get_project_costs,
    get_summary,
    healthcheck,
)

router = APIRouter(prefix="/costwise", tags=["costwise"])


@router.get("/summary")
async def costwise_summary(period: str = "30d", days: int | None = None):
    """Get costwise cost summary for a time period."""
    return get_summary(period=period, days=days)


@router.get("/daily")
async def costwise_daily(days: int = 30):
    """Get daily cost time series."""
    return {"daily": get_daily_costs(days)}


@router.get("/models")
async def costwise_models(days: int = 30):
    """Get cost breakdown by model."""
    return {"models": get_model_breakdown(days)}


@router.get("/tips")
async def costwise_tips(days: int = 30):
    """Get optimization recommendations from the costwise analyzer."""
    return {"tips": get_optimization_tips(days)}


@router.get("/agent/{agent_name}")
async def costwise_agent(agent_name: str, days: int = 30):
    """Get cost data for a specific agent."""
    return get_agent_costs(agent_name, days)


@router.get("/project/{project}")
async def costwise_project(project: str, days: int = 30):
    """Get cost data for a specific project."""
    return get_project_costs(project, days)


@router.get("/health")
async def costwise_health():
    """Check costwise backend health."""
    return healthcheck()


@router.get("/bloat")
async def costwise_bloat():
    """Get model bloat detection report with per-agent analysis."""
    return get_bloat_report()


@router.get("/efficiency")
async def costwise_efficiency(days: int = 30):
    """Get cost efficiency metrics for the system."""
    return get_efficiency_report(days)


@router.get("/export")
async def costwise_export(days: int = 30, fmt: str = "json"):
    """Export raw cost records as JSON or CSV."""
    from fastapi.responses import PlainTextResponse
    data = export_costs(days, fmt)
    if fmt == "csv":
        return PlainTextResponse(data, media_type="text/csv")
    return {"data": data}
