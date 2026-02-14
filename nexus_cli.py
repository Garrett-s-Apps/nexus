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
    nexus analyze <target_dir>     Analyze codebase for issues
    nexus generate-report <analysis-state.json> <output.docx>  Generate DOCX report
    nexus execute-all              Execute all pending findings
    nexus execute-priority <sev>   Execute findings by severity
    nexus execute-category <cat>   Execute findings by category
    nexus execute-item <item_id>   Execute a single finding
    nexus dashboard                Start progress visualization dashboard
    nexus self-analyze             Run self-analysis on Nexus codebase
    nexus self-fix                 Auto-fix LOW/MEDIUM severity issues
    nexus self-pr                  Create PRs for HIGH/CRITICAL issues
    nexus self-metrics             Show self-improvement trend
    nexus stop                     Stop the server
"""

import os
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


def _start_slack_webhook():
    """Start the Slack webhook server for interactive approvals."""
    import threading
    from src.config import get_key
    from src.slack.webhook import create_webhook_app

    # Get configuration
    signing_secret = get_key("SLACK_SIGNING_SECRET")
    if not signing_secret:
        print("Error: SLACK_SIGNING_SECRET not configured")
        print("Set SLACK_SIGNING_SECRET in ~/.nexus/.env.keys or as environment variable")
        sys.exit(1)

    webhook_port = int(os.environ.get("SLACK_APPROVAL_WEBHOOK_PORT", "3000"))

    # Create and start Flask app
    app = create_webhook_app(signing_secret)

    print(f"Starting Slack webhook server on port {webhook_port}...")
    print(f"Listening for interactive events at http://localhost:{webhook_port}/slack/interactive")
    print("Press Ctrl+C to stop.\n")

    try:
        app.run(host="127.0.0.1", port=webhook_port, debug=False)
    except KeyboardInterrupt:
        print("\nSlack webhook server stopped.")
        sys.exit(0)


def _stop_slack_webhook():
    """Stop the running Slack webhook server."""
    import signal
    import subprocess

    try:
        # Find and kill process on webhook port
        port = int(os.environ.get("SLACK_APPROVAL_WEBHOOK_PORT", "3000"))
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                if pid:
                    os.kill(int(pid), signal.SIGTERM)
            print(f"Slack webhook server stopped (killed PID(s): {', '.join(pids)})")
        else:
            print(f"No process found on port {port}")
    except (subprocess.TimeoutExpired, FileNotFoundError, ProcessLookupError) as e:
        print(f"Could not stop webhook server: {e}")
        sys.exit(1)


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

    elif command == "analyze" and len(sys.argv) >= 3:
        target_dir = sys.argv[2]
        if not os.path.isdir(target_dir):
            print(f"Error: Directory not found: {target_dir}", file=sys.stderr)
            sys.exit(1)

        focus_areas = sys.argv[3:] if len(sys.argv) > 3 else None

        print(f"Analyzing codebase: {target_dir}")
        if focus_areas:
            print(f"Focus areas: {', '.join(focus_areas)}")
        print("This may take a minute...\n")

        from src.agents.analyzer import AnalyzerAgent, load_analysis_state

        async def _run_analysis():
            try:
                analyzer = AnalyzerAgent("chief_architect")
            except Exception:
                # Fallback: run analysis without agent framework
                from src.agents.analyzer import AnalyzerAgent as _AA
                analyzer = _AA.__new__(_AA)
                analyzer.agent_id = "analyzer"
                analyzer.name = "Analyzer"
                analyzer.title = "Codebase Analyzer"
                analyzer.model = "claude-sonnet-4-20250514"
                analyzer._total_cost = 0.0
                analyzer._running = False

            return await analyzer.analyze_codebase(target_dir, focus_areas)

        try:
            result = asyncio.run(_run_analysis())
            summary = result["summary"]
            findings = result["findings"]

            print("=" * 60)
            print("CODEBASE ANALYSIS COMPLETE")
            print("=" * 60)
            print(f"\nTotal findings: {summary['totalFindings']}")
            print(f"\nBy severity:")
            for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                count = summary["bySeverity"].get(sev, 0)
                if count:
                    print(f"  {sev}: {count}")
            print(f"\nBy category:")
            for cat, count in sorted(summary["byCategory"].items()):
                print(f"  {cat}: {count}")

            print(f"\nState saved to: {result['state_path']}")
            print("\nTop findings:")
            for f in findings[:10]:
                print(f"  [{f.severity}] {f.id}: {f.title}")
                print(f"         Location: {f.location} | Effort: {f.effort} ({f.effort_hours})")

        except Exception as e:
            print(f"Error: Analysis failed - {e}", file=sys.stderr)
            sys.exit(1)

    elif command == "generate-report" and len(sys.argv) >= 4:
        analysis_state_path = sys.argv[2]
        output_path = sys.argv[3]

        if not os.path.isfile(analysis_state_path):
            print(f"Error: Analysis state file not found: {analysis_state_path}", file=sys.stderr)
            sys.exit(1)

        print(f"Generating DOCX report...")
        print(f"  Input: {analysis_state_path}")
        print(f"  Output: {output_path}")

        try:
            from src.reports.docx_generator import ReportGenerator
            generator = ReportGenerator()
            result_path = generator.generate_rebuild_report(analysis_state_path, output_path)
            print(f"\n✅ Report generated: {result_path}")
        except Exception as e:
            print(f"Error: Failed to generate report - {e}", file=sys.stderr)
            sys.exit(1)

    elif command == "execute-all":
        _execute_findings(filter_type="all")

    elif command == "execute-priority" and len(sys.argv) >= 3:
        severity = sys.argv[2].upper()
        if severity not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            print(f"Error: Invalid severity: {severity}. Use CRITICAL, HIGH, MEDIUM, or LOW.", file=sys.stderr)
            sys.exit(1)
        _execute_findings(filter_type="severity", filter_value=severity)

    elif command == "execute-category" and len(sys.argv) >= 3:
        category = sys.argv[2].upper()
        valid_cats = ("SEC", "PERF", "ARCH", "CODE", "UX", "DATA", "MAINT", "COMP")
        if category not in valid_cats:
            print(f"Error: Invalid category: {category}. Use one of: {', '.join(valid_cats)}", file=sys.stderr)
            sys.exit(1)
        _execute_findings(filter_type="category", filter_value=category)

    elif command == "execute-item" and len(sys.argv) >= 3:
        item_id = sys.argv[2].upper()
        _execute_findings(filter_type="item", filter_value=item_id)

    elif command == "dashboard":
        from src.dashboard.server import run_dashboard
        print("Starting NEXUS Dashboard on http://127.0.0.1:8080")
        print("Press Ctrl+C to stop")
        try:
            run_dashboard(host="127.0.0.1", port=8080, debug=False)
        except KeyboardInterrupt:
            print("\nDashboard stopped.")

    elif command == "self-analyze":
        print("Running self-analysis on Nexus codebase...")
        print("This may take a few minutes...\n")

        from src.self_improvement.analyzer import SelfImprovementLoop

        async def _run_self_analysis():
            loop = SelfImprovementLoop()
            return await loop.run_self_analysis()

        try:
            result = asyncio.run(_run_self_analysis())
            summary = result["summary"]
            findings = result["findings"]

            print("=" * 60)
            print("NEXUS SELF-ANALYSIS COMPLETE")
            print("=" * 60)
            print(f"\nTotal findings: {summary['totalFindings']}")
            print(f"\nBy severity:")
            for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                count = summary["bySeverity"].get(sev, 0)
                if count:
                    print(f"  {sev}: {count}")
            print(f"\nBy category:")
            for cat, count in sorted(summary["byCategory"].items()):
                print(f"  {cat}: {count}")

            print(f"\nState saved to: {result['state_path']}")
            print("\nTop self-improvement opportunities:")
            for f in findings[:10]:
                print(f"  [{f.severity}] {f.id}: {f.title}")
                print(f"         Location: {f.location} | Effort: {f.effort}")

        except Exception as e:
            print(f"Error: Self-analysis failed - {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    elif command == "self-fix":
        print("Auto-fixing LOW/MEDIUM severity issues in Nexus...")

        from src.self_improvement.analyzer import SelfImprovementLoop

        async def _run_auto_fix():
            loop = SelfImprovementLoop()
            return await loop.auto_fix_issues(max_severity="MEDIUM")

        try:
            result = asyncio.run(_run_auto_fix())

            print("=" * 60)
            print("AUTO-FIX COMPLETE")
            print("=" * 60)
            print(f"\nTotal auto-fixable issues: {result['total']}")
            print(f"Successfully fixed: {len(result['fixed'])}")
            print(f"Failed to fix: {len(result['failed'])}")

            if result['fixed']:
                print("\nFixed issues:")
                for finding_id in result['fixed']:
                    print(f"  ✅ {finding_id}")

            if result['failed']:
                print("\nFailed to fix:")
                for finding_id in result['failed']:
                    print(f"  ❌ {finding_id}")

        except Exception as e:
            print(f"Error: Auto-fix failed - {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    elif command == "self-pr":
        print("Creating PRs for HIGH/CRITICAL issues in Nexus...")

        from src.self_improvement.analyzer import SelfImprovementLoop

        async def _create_prs():
            loop = SelfImprovementLoop()
            return await loop.create_pr_for_high_severity()

        try:
            prs = asyncio.run(_create_prs())

            print("=" * 60)
            print("PR CREATION COMPLETE")
            print("=" * 60)
            print(f"\nCreated {len(prs)} PR(s):")

            for pr_url in prs:
                print(f"  📋 {pr_url}")

            if not prs:
                print("\nNo HIGH/CRITICAL issues found or PRs created.")

        except Exception as e:
            print(f"Error: PR creation failed - {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    elif command == "self-metrics":
        print("Loading self-improvement metrics...\n")

        from src.self_improvement.metrics import ImprovementMetrics

        try:
            metrics = ImprovementMetrics()
            trend = metrics.get_trend()

            if "message" in trend:
                print(trend["message"])
                sys.exit(0)

            print("=" * 60)
            print("NEXUS SELF-IMPROVEMENT TREND")
            print("=" * 60)
            print(f"\nTotal analyses: {trend['total_analyses']}")
            print(f"Time span: {trend['time_span_days']:.1f} days")
            print(f"Average effort per analysis: {trend['average_effort_hours']:.1f} hours")

            print("\n" + "-" * 60)
            print("TREND ANALYSIS")
            print("-" * 60)

            trend_data = trend["trend"]
            change = trend_data["findings_change"]
            change_pct = trend_data["findings_change_pct"]

            if trend_data["improving"]:
                print("✅ IMPROVING")
            else:
                print("⚠️  NEEDS ATTENTION")

            print(f"\nTotal findings change: {change:+d} ({change_pct:+.1f}%)")
            print(f"CRITICAL issues change: {trend_data['critical_change']:+d}")
            print(f"HIGH issues change: {trend_data['high_change']:+d}")

            print("\n" + "-" * 60)
            print("LATEST ANALYSIS")
            print("-" * 60)
            latest = trend["latest_analysis"]
            print(f"Date: {latest['timestamp'][:19]}")
            print(f"Total findings: {latest['total_findings']}")
            print("By severity:")
            for sev, count in latest.get("by_severity", {}).items():
                print(f"  {sev}: {count}")

        except Exception as e:
            print(f"Error: Failed to load metrics - {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    elif command == "slack-webhook":
        if len(sys.argv) < 3:
            print("Usage: nexus slack-webhook start|stop")
            print("  nexus slack-webhook start    Start the Slack webhook server")
            print("  nexus slack-webhook stop     Stop the Slack webhook server")
            sys.exit(1)

        subcommand = sys.argv[2]

        if subcommand == "start":
            _start_slack_webhook()
        elif subcommand == "stop":
            _stop_slack_webhook()
        else:
            print(f"Unknown subcommand: {subcommand}")
            print("Valid subcommands: start, stop")
            sys.exit(1)

    else:
        print(__doc__)


def _execute_findings(filter_type: str = "all", filter_value: str = ""):
    """Execute analysis findings as rebuild tasks."""
    import os as _os

    # Determine target dir from analysis state
    # Look in current dir and common locations
    target_dir = None
    for candidate in [_os.getcwd(), "/tmp/nexus-rebuild"]:
        state_path = _os.path.join(candidate, ".claude", "analysis-state.json")
        if _os.path.exists(state_path):
            target_dir = candidate
            break

    if not target_dir:
        print("Error: No analysis state found. Run 'nexus analyze <dir>' first.", file=sys.stderr)
        sys.exit(1)

    from src.agents.analyzer import (
        get_finding_by_id,
        get_findings_by_category,
        get_findings_by_severity,
        load_analysis_state,
        update_finding_status,
    )

    state = load_analysis_state(target_dir)
    if not state:
        print("Error: Could not load analysis state.", file=sys.stderr)
        sys.exit(1)

    if filter_type == "all":
        findings = [f for f in state["findings"] if f["status"] == "pending"]
    elif filter_type == "severity":
        findings = [f for f in get_findings_by_severity(target_dir, filter_value) if f["status"] == "pending"]
    elif filter_type == "category":
        findings = [f for f in get_findings_by_category(target_dir, filter_value) if f["status"] == "pending"]
    elif filter_type == "item":
        f = get_finding_by_id(target_dir, filter_value)
        findings = [f] if f else []
    else:
        findings = []

    if not findings:
        print("No pending findings match the criteria.")
        return

    # Sort by severity priority
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    findings.sort(key=lambda f: sev_order.get(f.get("severity", "LOW"), 3))

    print(f"\nExecuting {len(findings)} finding(s):\n")
    for f in findings:
        fid = f["id"]
        print(f"  [{f['severity']}] {fid}: {f['title']}")
        print(f"    Remediation: {f['remediation'][:120]}...")
        print(f"    Effort: {f['effort']} ({f['effort_hours']})")

        # Mark as in-progress
        update_finding_status(target_dir, fid, "in-progress")
        print(f"    Status: in-progress")
        print()

    print(f"\n{len(findings)} finding(s) marked as in-progress.")
    print("Use your preferred agent/workflow to implement the remediations.")
    print(f"Update status with: nexus execute-item <ID> (after fixing)")


if __name__ == "__main__":
    main()
