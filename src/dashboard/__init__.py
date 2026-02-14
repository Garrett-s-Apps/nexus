"""
NEXUS Progress Visualization Dashboard

Real-time web dashboard for monitoring:
- Task progress and dependency graphs (DAG)
- Cost tracking and budget status
- Active agents and their current work
- Live updates via Server-Sent Events
"""

from src.dashboard.server import run_dashboard

__all__ = ["run_dashboard"]
