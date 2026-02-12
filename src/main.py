"""
NEXUS v1.0 — Virtual Company

Starts the FastAPI server which manages the reasoning engine and Slack listener
via lifespan events. Everything boots from one command.

Run with: python -m src.main
"""

import uvicorn

from src.agents.org_chart import get_org_summary
from src.server.server import app


def main():
    print("""
    ╔══════════════════════════════════════════════╗
    ║            NEXUS VIRTUAL COMPANY             ║
    ║         Self-Orchestrating AI Org v1.0       ║
    ╠══════════════════════════════════════════════╣
    ║  Server:    http://127.0.0.1:4200            ║
    ║  Events:    http://127.0.0.1:4200/events     ║
    ║  State:     http://127.0.0.1:4200/state      ║
    ║  Org:       http://127.0.0.1:4200/org        ║
    ║  Slack:     #garrett-nexus                    ║
    ╚══════════════════════════════════════════════╝
    """)

    print(get_org_summary())
    print()

    uvicorn.run(app, host="127.0.0.1", port=4200, log_level="info")


if __name__ == "__main__":
    main()
