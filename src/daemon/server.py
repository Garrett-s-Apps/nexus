"""
NEXUS Daemon

FastAPI server running on localhost:4200. Single entry point for all clients.
Now with dynamic org management and CEO natural language interpretation.
"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel, Field

from src.agents.ceo_interpreter import execute_org_change, execute_question, interpret_ceo_input
from src.agents.org_chart_generator import generate_org_chart, update_org_chart_in_repo
from src.agents.registry import registry
from src.agents.sdk_bridge import cost_tracker, run_planning_agent, run_sdk_agent
from src.slack.notifier import notify, notify_completion, notify_demo, notify_escalation, notify_kpi

sessions: dict[str, dict] = {}
active_runs: dict[str, asyncio.Task] = {}


class MessageRequest(BaseModel):
    message: str
    source: Literal["slack", "ide", "cli", "api", "happy_coder"] = "api"
    project_path: str = ""
    session_id: str | None = None


class TalkRequest(BaseModel):
    agent_name: str
    message: str
    source: Literal["slack", "ide", "cli", "api", "happy_coder"] = "api"
    session_id: str | None = None


class StatusResponse(BaseModel):
    status: str
    active_sessions: int
    active_runs: int
    total_cost: float
    hourly_rate: float
    active_agents: int
    sessions: list[dict] = Field(default_factory=list)


async def execute_directive_bg(session_id: str, directive: str, project_path: str, source: str):
    try:
        notify(f"Received directive: _{directive}_\nStarting execution...")

        from src.orchestrator.graph import compile_nexus_dynamic
        nexus_app = compile_nexus_dynamic()

        from src.orchestrator.state import NexusState
        initial_state = NexusState(
            directive=directive,
            source=source,
            session_id=session_id,
            project_path=project_path or os.path.expanduser("~/Projects"),
        )

        config = {"configurable": {"thread_id": session_id}}
        result = await nexus_app.ainvoke(initial_state.model_dump(), config=config)

        sessions[session_id]["state"] = result
        sessions[session_id]["status"] = "complete"

        if result.get("demo_summary"):
            notify_demo(
                project=project_path or "NEXUS Project",
                summary=result["demo_summary"],
                metrics=result.get("demo_metrics", {}),
            )
        else:
            notify_completion(
                project=project_path or "NEXUS Project",
                feature=directive[:50],
                cost=result.get("cost", {}).get("total_cost_usd", 0),
            )

    except Exception as e:
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = str(e)
        notify_escalation("orchestrator", f"Execution failed: {str(e)}")

    finally:
        if session_id in active_runs:
            del active_runs[session_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not registry.is_initialized():
        registry.load_from_yaml()
        notify("NEXUS initialized from default org structure.")

    nexus_path = os.path.expanduser("~/Projects/nexus")
    if os.path.exists(nexus_path):
        update_org_chart_in_repo(nexus_path)

    notify("NEXUS daemon started. All systems operational.")
    yield
    notify("NEXUS daemon shutting down.")


app = FastAPI(
    title="NEXUS Daemon",
    description="Enterprise multi-agent orchestration system",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0", "active_agents": len(registry.get_active_agents())}


@app.get("/status", response_model=StatusResponse)
async def status():
    return StatusResponse(
        status="running",
        active_sessions=len(sessions),
        active_runs=len(active_runs),
        total_cost=cost_tracker.total_cost,
        hourly_rate=cost_tracker.hourly_rate,
        active_agents=len(registry.get_active_agents()),
        sessions=[
            {
                "id": sid,
                "directive": s.get("directive", ""),
                "status": s.get("status", "unknown"),
                "source": s.get("source", "unknown"),
            }
            for sid, s in sessions.items()
        ],
    )


@app.post("/message")
async def handle_message(req: MessageRequest, background_tasks: BackgroundTasks):
    session_id = req.session_id or str(uuid.uuid4())

    intent = await interpret_ceo_input(req.message)
    category = intent.get("category", "DIRECTIVE")
    summary = intent.get("summary", req.message[:100])

    if category == "ORG_CHANGE":
        result_text = await execute_org_change(intent)

        if req.source == "slack":
            notify(f"*Org Change:* {summary}\n\n{result_text}")

        return {
            "session_id": session_id,
            "category": "ORG_CHANGE",
            "summary": summary,
            "result": result_text,
            "org_summary": registry.get_org_summary(),
            "cost": intent.get("_cost", 0),
        }

    elif category == "QUESTION":
        answer = await execute_question(intent)

        if req.source == "slack":
            notify(f"*Q:* {summary}\n\n{answer[:2000]}")

        return {
            "session_id": session_id,
            "category": "QUESTION",
            "summary": summary,
            "answer": answer,
            "cost": intent.get("_cost", 0),
        }

    elif category == "COMMAND":
        command = intent.get("details", {}).get("command", "status")
        return await run_command_internal(command, intent.get("details", {}).get("args", ""), req.source)

    else:
        sessions[session_id] = {
            "directive": req.message,
            "source": req.source,
            "project_path": req.project_path,
            "status": "running",
            "state": None,
            "error": None,
        }

        task = asyncio.create_task(
            execute_directive_bg(session_id, req.message, req.project_path, req.source)
        )
        active_runs[session_id] = task

        return {
            "session_id": session_id,
            "category": "DIRECTIVE",
            "summary": summary,
            "status": "started",
            "message": f"Directive received. The org is working on it. Session: {session_id}",
        }


@app.post("/talk")
async def talk_to_agent(req: TalkRequest):
    agent_key = req.agent_name.lower().replace("-", "_").replace(" ", "_")
    agent = registry.get_agent(agent_key)

    if not agent:
        found = registry.search_agents(req.agent_name)
        if found:
            agent = found[0]
            agent_key = agent.id
        else:
            available = [a.id for a in registry.get_active_agents()]
            return {"error": f"Unknown agent: {req.agent_name}. Available: {', '.join(available)}"}

    agent_config = agent.to_dict()

    if agent.spawns_sdk:
        result = await run_sdk_agent(
            agent_key,
            agent_config,
            req.message,
            sessions.get(req.session_id, {}).get("project_path", os.path.expanduser("~/Projects")),
        )
    else:
        result = await run_planning_agent(agent_key, agent_config, req.message)

    return {
        "agent": agent.name,
        "agent_id": agent.id,
        "response": result["output"],
        "cost": result["cost"],
        "model": result["model"],
    }


@app.get("/org")
async def get_org():
    return {
        "summary": registry.get_org_summary(),
        "reporting_tree": registry.get_reporting_tree(),
        "agents": [a.to_dict() for a in registry.get_active_agents()],
        "changelog": registry.get_changelog(20),
    }


@app.get("/org/chart")
async def get_org_chart():
    return {"chart": generate_org_chart()}


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    if session_id not in sessions:
        return {"error": "Session not found"}
    return sessions[session_id]


async def run_command_internal(command: str, args: str, source: str) -> dict:
    if command == "kpi":
        dashboard = _generate_kpi_dashboard()
        if source == "slack":
            notify_kpi(dashboard)
        return {"category": "COMMAND", "command": "kpi", "dashboard": dashboard}

    elif command == "cost":
        return {
            "category": "COMMAND",
            "command": "cost",
            "total_cost": cost_tracker.total_cost,
            "hourly_rate": cost_tracker.hourly_rate,
            "by_model": cost_tracker.by_model,
            "by_agent": cost_tracker.by_agent,
            "over_budget": cost_tracker.over_budget,
        }

    elif command == "status":
        if args and "org" in args:
            org_data = await get_org()
            org_data["category"] = "COMMAND"
            return org_data
        result = (await status()).model_dump()
        result["category"] = "COMMAND"
        return result

    elif command == "org":
        org_data = await get_org()
        org_data["category"] = "COMMAND"
        return org_data

    else:
        return {"category": "COMMAND", "error": f"Unknown command: {command}"}


def _generate_kpi_dashboard() -> str:
    agents = registry.get_active_agents()
    return f"""
NEXUS Performance Dashboard
{'=' * 50}

ORGANIZATION
  Active Agents:      {len(agents)}
  Executive:          {len([a for a in agents if a.layer == 'executive'])}
  Management:         {len([a for a in agents if a.layer == 'management'])}
  Senior:             {len([a for a in agents if a.layer == 'senior'])}
  Implementation:     {len([a for a in agents if a.layer == 'implementation'])}
  Quality:            {len([a for a in agents if a.layer == 'quality'])}
  Consultants:        {len([a for a in agents if a.layer == 'consultant'])}

COST
  Total Spend:        ${cost_tracker.total_cost:.2f}
  Hourly Rate:        ${cost_tracker.hourly_rate:.2f}/hr (target: $1.00/hr)
  Over Budget:        {'YES' if cost_tracker.over_budget else 'No'}

  By Model:
{chr(10).join(f'    {m}: ${c:.4f}' for m, c in cost_tracker.by_model.items())}

  By Agent:
{chr(10).join(f'    {a}: ${c:.4f}' for a, c in cost_tracker.by_agent.items())}

SESSIONS
  Active Sessions:    {len(sessions)}
  Active Runs:        {len(active_runs)}

{'=' * 50}
"""


def start_daemon(host: str = "127.0.0.1", port: int = 4200):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_daemon()
