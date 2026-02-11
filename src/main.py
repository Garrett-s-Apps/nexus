"""
NEXUS Entry Point

Starts both the FastAPI server and the Slack listener.
Run with: python -m src.main
"""

import asyncio
import uvicorn
import threading
from src.server.server import app
from src.slack.listener import start_slack_listener


def run_server():
    """Run the FastAPI server in a thread."""
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
    ║  Server:  http://127.0.0.1:4200         ║
    ║  Slack:   #garrett-nexus                 ║
    ║  Status:  http://127.0.0.1:4200/status  ║
    ╚══════════════════════════════════════════╝
    """)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    try:
        asyncio.run(run_slack())
    except KeyboardInterrupt:
        print("\nNEXUS shutting down...")


if __name__ == "__main__":
    main()
