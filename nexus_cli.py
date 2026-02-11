#!/usr/bin/env python3
"""
NEXUS CLI

Usage:
    nexus start              Start the server + Slack listener
    nexus status             Show active workstreams
    nexus kpi                Show KPI dashboard
    nexus cost               Show cost report
    nexus talk <agent> <msg> Talk to a specific agent
    nexus directive <text>   Submit a directive
    nexus stop               Stop the server
"""

import sys
import asyncio
import aiohttp

SERVER_URL = "http://127.0.0.1:4200"


async def call_server(method: str, path: str, json: dict = None):
    async with aiohttp.ClientSession() as session:
        try:
            if method == "GET":
                async with session.get(f"{SERVER_URL}{path}") as resp:
                    return await resp.json()
            else:
                async with session.post(f"{SERVER_URL}{path}", json=json) as resp:
                    return await resp.json()
        except aiohttp.ClientError:
            return {"error": "NEXUS server is not running. Start with: nexus start"}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]

    if command == "start":
        from src.main import main as start_main
        start_main()

    elif command == "status":
        result = asyncio.run(call_server("GET", "/status"))
        if "error" in result:
            print(result["error"])
        else:
            print(f"Status: {result['status']}")
            print(f"Active Sessions: {result['active_sessions']}")
            print(f"Active Runs: {result['active_runs']}")
            print(f"Total Cost: ${result['total_cost']:.2f}")
            print(f"Hourly Rate: ${result['hourly_rate']:.2f}/hr")
            for s in result.get("sessions", []):
                print(f"  [{s['status']}] {s['directive'][:60]}")

    elif command == "kpi":
        result = asyncio.run(call_server("POST", "/command", {"command": "kpi", "source": "cli"}))
        if "error" in result:
            print(result["error"])
        else:
            print(result.get("dashboard", ""))

    elif command == "cost":
        result = asyncio.run(call_server("POST", "/command", {"command": "cost", "source": "cli"}))
        if "error" in result:
            print(result["error"])
        else:
            print(f"Total Cost: ${result['total_cost']:.2f}")
            print(f"Hourly Rate: ${result['hourly_rate']:.2f}/hr")
            print(f"Over Budget: {result['over_budget']}")
            print("\nBy Model:")
            for m, c in result.get("by_model", {}).items():
                print(f"  {m}: ${c:.4f}")
            print("\nBy Agent:")
            for a, c in result.get("by_agent", {}).items():
                print(f"  {a}: ${c:.4f}")

    elif command == "talk" and len(sys.argv) >= 4:
        agent = sys.argv[2]
        message = " ".join(sys.argv[3:])
        result = asyncio.run(call_server("POST", "/talk", {
            "agent_name": agent,
            "message": message,
            "source": "cli",
        }))
        if "error" in result:
            print(result["error"])
        else:
            print(f"\n{result.get('agent', agent)}:")
            print(result.get("response", "No response"))
            print(f"\n[Cost: ${result.get('cost', 0):.4f}]")

    elif command == "directive":
        directive = " ".join(sys.argv[2:])
        result = asyncio.run(call_server("POST", "/directive", {
            "directive": directive,
            "source": "cli",
        }))
        if "error" in result:
            print(result["error"])
        else:
            print(f"Session: {result['session_id']}")
            print(f"Status: {result['status']}")
            print("NEXUS is working. You'll be notified via Slack when complete.")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
