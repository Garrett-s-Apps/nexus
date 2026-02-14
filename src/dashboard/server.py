"""
NEXUS Progress Visualization Dashboard

Real-time web dashboard showing:
- Task progress and dependency graph (DAG)
- Cost tracking
- Active agents
- Live updates via Server-Sent Events
"""

import json
import logging
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, Response
from flask_cors import CORS

from src.cost.tracker import cost_tracker
from src.memory.store import Memory

logger = logging.getLogger("nexus.dashboard.server")

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
CORS(app)

# Global memory instance
memory = Memory()


def get_active_agents():
    """Get list of active agents from memory."""
    try:
        working = memory.get_working_agents()
        return [
            {
                "id": agent["agent_id"],
                "name": agent["name"],
                "role": agent["role"],
                "status": agent["status"],
                "current_task": agent.get("current_task", ""),
                "last_action": agent.get("last_action", "")[:100],
            }
            for agent in working
        ]
    except Exception as e:
        logger.error(f"Failed to get active agents: {e}")
        return []


@app.route("/")
def dashboard():
    """Main dashboard page."""
    return render_template("dashboard.html")


@app.route("/api/status")
def get_status():
    """Get current project status."""
    try:
        directive = memory.get_active_directive()

        if not directive:
            # No active directive
            tasks = []
            execution_order = []
        else:
            tasks = memory.get_board_tasks(directive["id"])
            execution_order = memory.get_execution_order(directive["id"])

        # Count tasks by status
        completed = len([t for t in tasks if t["status"] == "complete"])
        in_progress = len([t for t in tasks if t["status"] == "in_progress"])
        claimed = len([t for t in tasks if t["status"] == "claimed"])
        blocked = len([t for t in tasks if t.get("depends_on") and json.loads(t.get("depends_on", "[]"))])

        status = {
            "directive": {
                "id": directive["id"] if directive else "",
                "text": directive["text"][:200] if directive else "No active directive",
                "status": directive["status"] if directive else "idle",
            } if directive else None,
            "tasks": {
                "total": len(tasks),
                "completed": completed,
                "in_progress": in_progress + claimed,
                "available": len([t for t in tasks if t["status"] == "available"]),
                "blocked": blocked,
            },
            "cost": {
                "total": cost_tracker.total_cost,
                "hourly_rate": cost_tracker.hourly_rate,
                "budget_remaining": cost_tracker.budgets["session_hard_cap"] - cost_tracker.total_cost,
                "over_budget": cost_tracker.over_budget,
            },
            "agents": {
                "active": get_active_agents(),
                "count": len(get_active_agents()),
            },
            "dag": {
                "levels": execution_order,
                "level_count": len(execution_order),
            },
        }

        return jsonify(status)
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/task-dag")
def get_task_dag():
    """Get task dependency graph as Mermaid."""
    try:
        directive = memory.get_active_directive()

        if not directive:
            mermaid = "graph TD\n  empty[No active directive]"
        else:
            mermaid = memory.export_task_dag_mermaid(directive["id"])

        return jsonify({"mermaid": mermaid})
    except Exception as e:
        logger.error(f"Failed to export DAG: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/events")
def events():
    """Server-Sent Events stream for real-time updates."""
    def event_stream():
        """Generator that yields SSE events."""
        last_event_id = memory.get_latest_event_id()

        while True:
            import time
            time.sleep(2)  # Poll every 2 seconds

            try:
                # Get new events since last check
                new_events = memory.get_events_since(last_event_id, limit=50)

                if new_events:
                    last_event_id = new_events[-1]["id"]

                    for event in new_events:
                        # Send event to client
                        yield f"data: {json.dumps(event)}\n\n"

                # Also send periodic status updates
                status = get_status().json
                yield f"event: status\ndata: {json.dumps(status)}\n\n"

            except Exception as e:
                logger.error(f"Event stream error: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/api/cost-report")
def get_cost_report():
    """Get detailed cost report."""
    try:
        summary = cost_tracker.get_summary()
        daily = cost_tracker.get_daily_breakdown(7)

        return jsonify({
            "summary": summary,
            "daily": daily,
            "report": cost_tracker.generate_cfo_report(),
        })
    except Exception as e:
        logger.error(f"Failed to get cost report: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks")
def get_tasks():
    """Get all tasks for the active directive."""
    try:
        directive = memory.get_active_directive()

        if not directive:
            return jsonify({"tasks": []})

        tasks = memory.get_board_tasks(directive["id"])

        # Format tasks for frontend
        task_list = [
            {
                "id": t["id"],
                "title": t["title"],
                "description": t.get("description", ""),
                "status": t["status"],
                "claimed_by": t.get("claimed_by"),
                "depends_on": json.loads(t.get("depends_on", "[]")),
                "blocks": json.loads(t.get("blocks", "[]")),
                "priority": t.get("priority", 0),
                "created_at": t["created_at"],
                "updated_at": t["updated_at"],
                "output": t.get("output", ""),
            }
            for t in tasks
        ]

        return jsonify({"tasks": task_list})
    except Exception as e:
        logger.error(f"Failed to get tasks: {e}")
        return jsonify({"error": str(e)}), 500


def run_dashboard(host="127.0.0.1", port=8080, debug=False):
    """Start the dashboard server."""
    # Initialize memory
    if not memory._conn:
        memory.init()

    logger.info(f"Starting dashboard server on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run_dashboard(debug=True)
