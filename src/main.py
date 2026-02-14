"""
NEXUS v1.0 — Virtual Company

Starts the FastAPI server which manages the reasoning engine and Slack listener
via lifespan events. Everything boots from one command.

Run with: python -m src.main
"""

import os

import uvicorn

from src.agents.org_chart import get_org_summary
from src.config import NEXUS_DIR
from src.observability.logging import configure_logging
from src.server.server import app


def main():
    # Initialize structured logging before anything else
    configure_logging(os.path.join(NEXUS_DIR, "logs"))

    # Binds to all interfaces for container/Docker deployment.
    # In production, place behind a reverse proxy with TLS termination.
    host = os.environ.get("NEXUS_HOST", "0.0.0.0")  # noqa: S104
    port = int(os.environ.get("NEXUS_PORT", "4200"))
    local = f"http://localhost:{port}"
    print(f"""
    ╔══════════════════════════════════════════════╗
    ║            NEXUS VIRTUAL COMPANY             ║
    ║         Self-Orchestrating AI Org v1.0       ║
    ╠══════════════════════════════════════════════╣
    ║  Server:    {local:<34}║
    ║  Dashboard: {local + '/dashboard':<34}║
    ║  Slack:     #garrett-nexus                    ║
    ╚══════════════════════════════════════════════╝
    """)

    print(get_org_summary())
    print()

    # SEC-014: Add request size limits, concurrency limits, and timeouts
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        limit_concurrency=1000,
        limit_max_requests=10000,
        timeout_keep_alive=5,
    )


if __name__ == "__main__":
    main()
