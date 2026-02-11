"""
NEXUS Entry Point

Starts both the FastAPI daemon and the Slack listener.
Run with: python -m src.main
"""

import asyncio
import uvicorn
import threading
from src.daemon.server import app
from src.slack.listener import start_slack_listener


def run_daemon():
    """Run the FastAPI daemon in a thread."""
    uvicorn.run(app, host="127.0.0.1", port=4200, log_level="info")


async def run_slack():
    """Run the Slack listener."""
    await start_slack_listener()


def main():
    print("""
    ╔══════════════════════════════════════════╗
    ║           NEXUS ORCHESTRATOR             ║
    ║   Enterprise Multi-Agent System v0.1.0   ║
    ╠══════════════════════════════════════════╣
    ║  Daemon:  http://127.0.0.1:4200         ║
    ║  Slack:   #garrett-nexus                 ║
    ║  Status:  http://127.0.0.1:4200/status  ║
    ╚══════════════════════════════════════════╝
    """)

    daemon_thread = threading.Thread(target=run_daemon, daemon=True)
    daemon_thread.start()

    try:
        asyncio.run(run_slack())
    except KeyboardInterrupt:
        print("\nNEXUS shutting down...")


if __name__ == "__main__":
    main()
