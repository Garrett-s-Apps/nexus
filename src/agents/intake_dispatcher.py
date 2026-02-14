"""
NEXUS Intake Dispatcher

Executes tool calls from Haiku intake by invoking existing NEXUS services.
Returns results that can be sent back to Haiku for natural language formatting,
or directly to the user.
"""

import json
import logging

from src.agents.haiku_intake import IntakeResult
from src.agents.org_chart_generator import update_org_chart_in_repo
from src.agents.registry import registry
from src.cost.tracker import cost_tracker
from src.kpi.tracker import kpi_tracker
from src.memory.store import memory
from src.ml.similarity import analyze_new_directive, format_briefing
from src.ml.store import ml_store

logger = logging.getLogger("nexus.intake_dispatcher")


async def dispatch(
    result: IntakeResult, source: str = "slack", thread_ts: str = ""
) -> str:
    """
    Dispatch a tool call from Haiku intake to the appropriate NEXUS service.

    Args:
        result: The IntakeResult from Haiku
        source: Where the request came from (slack, cli, etc)
        thread_ts: Thread timestamp for Slack threading

    Returns:
        Formatted string result to send back to user or Haiku
    """
    if not result.tool_called:
        # Pure conversation, return Haiku's response as-is
        return result.response_text

    tool_name = result.tool_called
    tool_input = result.tool_input or {}

    logger.info(f"Dispatching tool: {tool_name} with input: {tool_input}")

    # Emit event for dashboard live ticker
    memory.emit_event("intake", tool_name, {
        "input": {k: str(v)[:100] for k, v in tool_input.items()},
        "source": source,
    })

    # Route to appropriate handler
    handler = DISPATCH_MAP.get(tool_name)
    if not handler:
        return f"Error: Unknown tool '{tool_name}'"

    try:
        output: str = await handler(tool_input)
        return output
    except Exception as e:
        logger.exception(f"Error dispatching {tool_name}: {e}")
        return f"Error executing {tool_name}: {e}"


# ============================================
# TOOL HANDLERS
# ============================================


async def handle_query_org(params: dict) -> str:
    """Handle org structure queries."""
    query_type = params.get("query_type")
    agent_id = params.get("agent_id")

    if query_type == "full_org":
        org_summary: str = registry.get_org_summary()
        return org_summary

    if query_type == "agent_detail":
        if not agent_id:
            return "Error: agent_id required for agent_detail query"
        agent = registry.get_agent(agent_id)
        if not agent:
            return f"Agent '{agent_id}' not found"
        return json.dumps(agent.to_dict(), indent=2)

    if query_type == "team":
        # Get all agents by layer
        layers = ["executive", "management", "senior", "implementation", "quality", "consultant"]
        lines = []
        for layer in layers:
            agents = registry.get_agents_by_layer(layer)
            if agents:
                lines.append(f"\n{layer.upper()} LAYER:")
                for a in agents:
                    lines.append(f"  - {a.name} ({a.id}) [{a.model}]")
        return "\n".join(lines) if lines else "No agents found"

    if query_type == "reporting_tree":
        tree: str = registry.get_reporting_tree("ceo")
        return tree

    return f"Error: Unknown query_type '{query_type}'"


async def handle_mutate_org(params: dict) -> str:
    """Handle org mutations: hire, fire, promote, reassign."""
    action = params.get("action")
    agent_id = params.get("agent_id")
    action_params = params.get("params", {})

    # Get project path for org chart updates
    import os
    project_path = os.environ.get(
        "NEXUS_PROJECT_PATH", os.path.expanduser("~/Projects/nexus")
    )

    if action == "hire":
        # Hire a new agent
        new_agent = action_params
        required = ["agent_id", "name", "model", "layer", "description", "system_prompt"]
        if not all(k in new_agent for k in required):
            return f"Error: Missing required fields for hire: {required}"

        agent = registry.hire_agent(
            agent_id=new_agent["agent_id"],
            name=new_agent["name"],
            model=new_agent["model"],
            layer=new_agent["layer"],
            description=new_agent["description"],
            system_prompt=new_agent["system_prompt"],
            tools=new_agent.get("tools", []),
            spawns_sdk=new_agent.get("spawns_sdk", False),
            reports_to=new_agent.get("reports_to"),
            provider=new_agent.get("provider", "anthropic"),
            temporary=new_agent.get("temporary", False),
            temp_duration_hours=new_agent.get("temp_duration_hours"),
        )
        update_org_chart_in_repo(project_path)
        return f"Hired {agent.name} ({agent.id}) as {agent.layer} agent, model={agent.model}"

    if action == "fire":
        if not agent_id:
            return "Error: agent_id required for fire action"
        success = registry.fire_agent(agent_id, reason="CEO decision")
        if success:
            update_org_chart_in_repo(project_path)
            return f"Fired agent '{agent_id}'"
        return f"Error: Could not fire agent '{agent_id}' (not found or already fired)"

    if action == "promote":
        if not agent_id:
            return "Error: agent_id required for promote action"
        new_model = action_params.get("new_model")
        if not new_model:
            return "Error: new_model required in params for promote"
        success = registry.promote_agent(agent_id, new_model)
        if success:
            update_org_chart_in_repo(project_path)
            return f"Promoted agent '{agent_id}' to {new_model}"
        return f"Error: Could not promote agent '{agent_id}'"

    if action == "reassign":
        if not agent_id:
            return "Error: agent_id required for reassign action"
        new_manager = action_params.get("new_manager")
        if not new_manager:
            return "Error: new_manager required in params for reassign"
        success = registry.reassign_agent(agent_id, new_manager)
        if success:
            update_org_chart_in_repo(project_path)
            return f"Reassigned agent '{agent_id}' to report to '{new_manager}'"
        return f"Error: Could not reassign agent '{agent_id}'"

    if action == "update_model":
        if not agent_id:
            return "Error: agent_id required for update_model action"
        new_model = action_params.get("new_model")
        if not new_model:
            return "Error: new_model required in params for update_model"
        success = registry.update_agent(agent_id, model=new_model)
        if success:
            update_org_chart_in_repo(project_path)
            return f"Updated agent '{agent_id}' to use model {new_model}"
        return f"Error: Could not update agent '{agent_id}'"

    return f"Error: Unknown action '{action}'"


async def handle_query_status(params: dict) -> str:
    """Handle system status queries."""
    detail_level = params.get("detail_level", "summary")

    # Get active directive
    directive = memory.get_active_directive()
    status_lines = []

    if directive:
        status_lines.append(f"ACTIVE DIRECTIVE: {directive['text'][:100]}")
        status_lines.append(f"Status: {directive['status']}")
        status_lines.append(f"ID: {directive['id']}")
    else:
        status_lines.append("No active directive")

    # Recent events
    if detail_level == "detailed":
        events = memory.get_recent_events(limit=10)
        if events:
            status_lines.append("\nRECENT EVENTS:")
            for evt in events:
                status_lines.append(f"  [{evt['source']}] {evt['event_type']}: {evt.get('data', '')[:80]}")

    # Running services
    services = memory.get_running_services()
    if services:
        status_lines.append("\nRUNNING SERVICES:")
        for svc in services:
            status_lines.append(f"  - {svc['name']}: {svc.get('url', 'n/a')} (status: {svc['status']})")

    # Working agents
    working = memory.get_working_agents()
    if working:
        status_lines.append(f"\nAGENTS WORKING: {len(working)}")
        if detail_level == "detailed":
            for agent in working:
                status_lines.append(f"  - {agent['name']}: {agent.get('last_action', '')[:60]}")

    return "\n".join(status_lines) if status_lines else "System idle"


async def handle_query_cost(params: dict) -> str:
    """Handle cost queries."""
    scope = params.get("scope", "session")

    if scope == "session":
        return f"""Session Cost Report:
  Total: ${cost_tracker.total_cost:.2f}
  Hourly Rate: ${cost_tracker.hourly_rate:.2f}/hr
  API Calls: {cost_tracker.call_count}
  Target: $1.00/hr
  Status: {'✅ On budget' if cost_tracker.hourly_rate <= 1.0 else '⚠️ Over budget'}"""

    if scope in ("today", "month"):
        monthly = cost_tracker.get_monthly_cost()
        return f"""Monthly Cost Report:
  Month-to-Date: ${monthly:.2f}
  Target: ${cost_tracker.budgets['monthly_target']:.2f}
  Hard Cap: ${cost_tracker.budgets['monthly_hard_cap']:.2f}
  Status: {'✅' if monthly <= cost_tracker.budgets['monthly_target'] else '⚠️'}"""

    if scope == "all_time":
        # For all-time, we'd need to query the cost DB
        # For now, return session + monthly
        monthly = cost_tracker.get_monthly_cost()
        return f"""Cost Summary:
  Session: ${cost_tracker.total_cost:.2f}
  This Month: ${monthly:.2f}
  (All-time stats would require historical DB query)"""

    return f"Error: Unknown scope '{scope}'"


async def handle_query_kpi(params: dict) -> str:
    """Handle KPI queries."""
    category = params.get("category", "all")

    if category == "all":
        dashboard: str = kpi_tracker.generate_dashboard(hours=24)
        return dashboard

    # For specific categories, get summary and filter
    summary = kpi_tracker.get_summary(hours=24)

    if category == "productivity":
        return f"""Productivity Metrics (24h):
  Tasks Completed: {summary['tasks_completed']}
  PRs Created: {summary['total_prs']}"""

    if category == "quality":
        return f"""Quality Metrics (24h):
  Lint Pass Rate: {summary['lint_pass_rate']:.0f}%
  First-Try PR Approval: {summary['first_try_approval_rate']:.0f}%"""

    if category == "cost":
        return f"""Cost Metrics (24h):
  Period Spend: ${summary['total_cost']:.2f}
  Current Hourly: ${cost_tracker.hourly_rate:.2f}/hr"""

    if category == "security":
        # Security metrics would need to be tracked separately
        return "Security metrics: No data available yet"

    if category == "trends":
        # Would need time-series analysis
        return "Trend analysis: Not yet implemented"

    return f"Error: Unknown category '{category}'"


async def handle_query_ml(params: dict) -> str:
    """Handle ML system queries."""
    query_type = params.get("query_type")
    text = params.get("text")
    agent_id = params.get("agent_id")

    if query_type == "status":
        counts = ml_store.get_training_data_count()
        return f"""ML System Status:
  Task Outcomes: {counts['task_outcomes']}
  Directive Embeddings: {counts['directive_embeddings']}
  Escalation Events: {counts['escalation_events']}
  Status: {'Ready' if counts['task_outcomes'] > 10 else 'Collecting data'}"""

    if query_type == "similar_directives":
        if not text:
            return "Error: text required for similar_directives query"
        analysis = analyze_new_directive(text)
        briefing: str = format_briefing(analysis)
        return briefing

    if query_type == "agent_stats":
        if not agent_id:
            return "Error: agent_id required for agent_stats query"
        stats = ml_store.get_agent_success_rate(agent_id)
        return f"""Agent Performance Stats: {agent_id}
  Total Tasks: {stats['total_tasks']}
  Success Rate: {stats['success_rate']:.0%}
  Avg Cost: ${stats['avg_cost']:.4f}
  Avg Defects: {stats['avg_defects']:.2f}"""

    return f"Error: Unknown query_type '{query_type}'"


async def handle_start_directive(params: dict) -> str:
    """Handle directive start requests.

    This is special — the actual orchestration happens in the caller (listener.py).
    We just return a marker string so the caller knows to hand off to the orchestrator.
    """
    directive_text = params.get("directive_text", "")
    priority = params.get("priority", "medium")
    context = params.get("context", "")

    if not directive_text:
        return "Error: directive_text is required"

    # Return a marker that the caller can parse
    return f"DIRECTIVE:{priority}:{directive_text}|CONTEXT:{context}"


async def handle_generate_document(params: dict) -> str:
    """Handle document generation requests.

    Like start_directive, this is handled by the caller.
    """
    doc_type = params.get("document_type", "docx")
    description = params.get("description", "")

    if not description:
        return "Error: description is required"

    return f"DOCUMENT:{doc_type}:{description}"


async def handle_talk_to_agent(params: dict) -> str:
    """Handle direct agent messaging."""
    agent_id = params.get("agent_id")
    message = params.get("message")

    if not agent_id:
        return "Error: agent_id is required"
    if not message:
        return "Error: message is required"

    # Look up the agent
    agent = registry.get_agent(agent_id)
    if not agent:
        return f"Error: Agent '{agent_id}' not found"

    # For now, we don't have a direct agent messaging system
    # This would require spawning a planning or SDK agent
    # Return a placeholder
    return f"Message queued for {agent.name}: {message[:100]}"


async def handle_query_database(params: dict) -> str:
    """Handle database queries across NEXUS internal stores."""
    table = params.get("table", "")
    filter_val = params.get("filter", "recent")
    limit = min(params.get("limit", 20) or 20, 50)

    if table == "directives":
        directives = memory.get_recent_directives(limit=limit)
        if not directives:
            return "No directives found."
        lines = [f"DIRECTIVES ({len(directives)} results):"]
        for d in directives:
            lines.append(
                f"  [{d.get('status', '?')}] {d.get('id', '?')[:8]}... "
                f"| {d.get('text', '')[:80]} "
                f"| created: {d.get('created_at', '?')}"
            )
        return "\n".join(lines)

    elif table == "events":
        limit_val = 50 if filter_val == "all" else limit
        events = memory.get_recent_events(limit=limit_val)
        if not events:
            return "No events found."
        lines = [f"EVENTS ({len(events)} results):"]
        for e in events:
            data_str = str(e.get("data", ""))[:80]
            lines.append(
                f"  [{e.get('source', '?')}] {e.get('event_type', '?')} "
                f"| {data_str} | {e.get('timestamp', '?')}"
            )
        return "\n".join(lines)

    elif table == "sessions":
        from src.sessions.cli_pool import cli_pool as _pool
        sessions = _pool._sessions
        if not sessions:
            return "No active CLI sessions."
        lines = [f"ACTIVE CLI SESSIONS ({len(sessions)}):"]
        for ts, sess_list in sessions.items():
            for i, s in enumerate(sess_list):
                lines.append(
                    f"  thread: {ts}[{i}] | alive: {s.alive} "
                    f"| pid: {s.process.pid if s.process else 'none'}"
                )
        return "\n".join(lines)

    elif table == "memory":
        # Return project memory + stored context
        projects = memory.get_active_projects()
        context = memory.get_all_context()
        lines = []
        if projects:
            lines.append(f"ACTIVE PROJECTS ({len(projects)}):")
            for p in projects:
                lines.append(f"  {p.get('name', p.get('id', '?'))}: {p.get('description', '')[:80]}")
        if context:
            lines.append(f"\nSTORED CONTEXT ({len(context)} entries):")
            for c in context[:limit]:
                lines.append(f"  [{c.get('key', '?')}] {str(c.get('value', ''))[:100]}")
        return "\n".join(lines) if lines else "No memory entries found."

    elif table == "task_outcomes":
        outcomes = ml_store.get_outcomes(limit=limit)
        if not outcomes:
            return "No task outcomes recorded yet."
        lines = [f"TASK OUTCOMES ({len(outcomes)} results):"]
        for o in outcomes:
            lines.append(
                f"  [{o.get('outcome', '?')}] agent={o.get('agent_id', '?')} "
                f"| cost=${o.get('cost', 0):.4f} "
                f"| {o.get('directive_text', '')[:60]} "
                f"| {o.get('created_at', '?')}"
            )
        return "\n".join(lines)

    elif table == "cost_log":
        daily = cost_tracker.get_daily_breakdown(days=7)
        agents = cost_tracker.get_agent_breakdown()
        lines = [f"COST REPORT (session: ${cost_tracker.total_cost:.2f}, rate: ${cost_tracker.hourly_rate:.2f}/hr)"]
        if daily:
            lines.append("\nDAILY BREAKDOWN (last 7 days):")
            for d in daily:
                lines.append(f"  {d.get('date', '?')}: ${d.get('cost', 0):.2f} ({d.get('calls', 0)} calls)")
        if agents:
            lines.append("\nAGENT BREAKDOWN:")
            for a in agents[:15]:
                lines.append(f"  {a.get('agent', '?')}: ${a.get('cost', 0):.4f} ({a.get('calls', 0)} calls)")
        return "\n".join(lines)

    return f"Error: Unknown table '{table}'. Valid: directives, events, sessions, memory, task_outcomes, cost_log"


# ============================================
# DISPATCH MAP
# ============================================

DISPATCH_MAP = {
    "query_org": handle_query_org,
    "mutate_org": handle_mutate_org,
    "query_status": handle_query_status,
    "query_cost": handle_query_cost,
    "query_kpi": handle_query_kpi,
    "query_ml": handle_query_ml,
    "query_database": handle_query_database,
    "start_directive": handle_start_directive,
    "generate_document": handle_generate_document,
    "talk_to_agent": handle_talk_to_agent,
}
