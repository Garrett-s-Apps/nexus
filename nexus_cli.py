#!/usr/bin/env python3
"""
NEXUS CLI

Usage:
    nexus start                    Start the server + Slack listener
    nexus status                   Show active workstreams
    nexus kpi                      Show KPI dashboard
    nexus cost                     Show cost report
    nexus talk <agent> <msg>       Talk to a specific agent
    nexus directive <text>         Submit a directive
    nexus checkpoint save <name>   Save a manual checkpoint
    nexus checkpoint list          List all checkpoints
    nexus checkpoint restore <name> Restore a checkpoint
    nexus stop                     Stop the server
"""

import sys
import asyncio
import aiohttp
import re

SERVER_URL = "http://127.0.0.1:4200"

# SEC-012: Input validation constants
MAX_AGENT_NAME_LENGTH = 255
MAX_MESSAGE_LENGTH = 50000
MAX_DIRECTIVE_LENGTH = 50000
VALID_AGENT_NAME_PATTERN = r'^[a-zA-Z0-9_\-\.]+$'

# Dangerous patterns to block in user input
DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/',
    r'curl.*\|\s*bash',
    r'wget.*\|\s*sh',
    r'nc\s+-[le]',
    r'eval\s*\(',
    r'exec\s*\(',
    r'__import__\s*\(',
    r'subprocess\s*\.\s*call',
    r'subprocess\s*\.\s*Popen',
    r'os\s*\.\s*system',
]


def validate_agent_name(agent: str) -> str:
    """Validate agent name to prevent injection attacks.

    Args:
        agent: Agent name to validate

    Returns:
        Validated agent name

    Raises:
        ValueError: If agent name is invalid
    """
    if not agent or len(agent) > MAX_AGENT_NAME_LENGTH:
        raise ValueError(f"Agent name must be 1-{MAX_AGENT_NAME_LENGTH} characters")

    if not re.match(VALID_AGENT_NAME_PATTERN, agent):
        raise ValueError("Agent name contains invalid characters. Use only alphanumeric, dash, underscore, and period")

    return agent


def validate_message_input(message: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Validate and sanitize user message input.

    Args:
        message: Message to validate
        max_length: Maximum allowed message length

    Returns:
        Sanitized message

    Raises:
        ValueError: If message contains dangerous patterns or exceeds limits
    """
    if not message:
        raise ValueError("Message cannot be empty")

    if len(message) > max_length:
        raise ValueError(f"Message too long (max {max_length} characters)")

    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            raise ValueError(f"Message contains potentially dangerous pattern")

    # Strip control characters except newline, carriage return, tab
    message = ''.join(c for c in message if ord(c) >= 32 or c in '\n\r\t')

    return message


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
        try:
            agent = validate_agent_name(sys.argv[2])
            message = validate_message_input(" ".join(sys.argv[3:]))
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
        except ValueError as e:
            print(f"Error: Invalid input - {e}", file=sys.stderr)
            sys.exit(1)

    elif command == "directive":
        try:
            directive = validate_message_input(" ".join(sys.argv[2:]), MAX_DIRECTIVE_LENGTH)
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
        except ValueError as e:
            print(f"Error: Invalid input - {e}", file=sys.stderr)
            sys.exit(1)

    elif command == "checkpoint":
        from src.orchestrator.checkpoint import CheckpointManager
        checkpoint_mgr = CheckpointManager()

        if len(sys.argv) < 3:
            print("Usage:")
            print("  nexus checkpoint save <name>")
            print("  nexus checkpoint list")
            print("  nexus checkpoint restore <name>")
            sys.exit(1)

        subcommand = sys.argv[2]

        if subcommand == "save":
            if len(sys.argv) < 4:
                print("Error: Checkpoint name required")
                print("Usage: nexus checkpoint save <name>")
                sys.exit(1)
            name = sys.argv[3]
            checkpoint_mgr.save_checkpoint(name, manual=True)
            print(f"✅ Checkpoint saved: {name}")

        elif subcommand == "list":
            checkpoints = checkpoint_mgr.list_checkpoints()
            if not checkpoints:
                print("No checkpoints found.")
            else:
                print("\n" + "=" * 63)
                print("📸 CHECKPOINTS")
                print("=" * 63 + "\n")

                for cp in checkpoints:
                    marker = "📌" if cp["manual"] else "⏰"
                    print(f"{marker} {cp['name']}")
                    print(f"   Time: {cp['timestamp']}")
                    print(f"   Branch: {cp['branch']} | Uncommitted: {cp['uncommitted']} files")
                    print(f"   Cost: ${cp['cost']:.2f}\n")

        elif subcommand == "restore":
            if len(sys.argv) < 4:
                print("Error: Checkpoint name required")
                print("Usage: nexus checkpoint restore <name>")
                sys.exit(1)
            name = sys.argv[3]
            success = checkpoint_mgr.restore_checkpoint(name)
            if not success:
                sys.exit(1)

        else:
            print(f"Unknown checkpoint subcommand: {subcommand}")
            print("Valid subcommands: save, list, restore")
            sys.exit(1)

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
