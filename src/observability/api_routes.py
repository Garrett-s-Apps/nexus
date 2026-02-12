"""FastAPI routes for observability endpoints."""

from fastapi import APIRouter

from src.observability.metrics import get_agent_performance, get_daily_summary, get_health_snapshot

router = APIRouter(prefix="/metrics", tags=["observability"])


@router.get("/daily")
async def daily_metrics(days: int = 7):
    return {"metrics": get_daily_summary(days=days)}


@router.get("/agents")
async def agent_metrics(days: int = 7):
    return {"agents": get_agent_performance(days=days)}


@router.get("/health")
async def health_metrics():
    return get_health_snapshot()
