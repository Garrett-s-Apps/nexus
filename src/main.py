"""
NEXUS v1.0 — Virtual Company

Starts the FastAPI server which manages the reasoning engine and Slack listener
via lifespan events. Everything boots from one command.

Run with: python -m src.main
"""

import os

import uvicorn

from src.agents.org_chart import get_org_summary
from src.server.server import app


def main():
    host = os.environ.get("NEXUS_HOST", "0.0.0.0")
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

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
