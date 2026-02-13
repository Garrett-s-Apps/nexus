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

from fastapi import BackgroundTasks, FastAPI, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from src.agents.haiku_intake import run_haiku_intake
from src.agents.intake_dispatcher import dispatch
from src.agents.org_chart_generator import generate_org_chart, update_org_chart_in_repo
from src.agents.registry import registry
from src.agents.sdk_bridge import cost_tracker, run_planning_agent, run_sdk_agent
from src.security.auth_gate import verify_session
from src.slack.notifier import notify, notify_completion, notify_demo, notify_escalation, notify_kpi

sessions: dict[str, dict] = {}
active_runs: dict[str, asyncio.Task] = {}

AUTH_COOKIE = "nexus_session"
_PUBLIC_PATHS = {"/health"}
_TOKEN_HEADER = "Authorization"  # noqa: S105 — header name, not a password


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
            source=source,  # type: ignore[arg-type]
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


@app.middleware("http")
async def auth_gate_middleware(request: Request, call_next):
    """Reject unauthenticated requests to protected routes."""
    path = request.url.path
    if path in _PUBLIC_PATHS:
        return await call_next(request)

    session_id = request.cookies.get(AUTH_COOKIE)
    if not session_id:
        auth_header = request.headers.get(_TOKEN_HEADER, "")
        if auth_header.startswith("Bearer "):
            session_id = auth_header[7:]

    user_agent = request.headers.get("user-agent", "")
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "127.0.0.1"
    )

    if not verify_session(session_id, user_agent=user_agent, client_ip=client_ip):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return await call_next(request)


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

    # Get org context for Haiku intake
    org_summary = registry.get_org_summary()

    # Run Haiku intake
    intake_result = await run_haiku_intake(
        message=req.message,
        org_summary=org_summary,
        system_status_brief=f"Source: {req.source}",
    )

    tool = intake_result.tool_called

    # Record intake event for ML feedback
    try:
        from src.ml.feedback import record_intake_event
        record_intake_event(
            message_text=req.message,
            tool_called=tool,
            tokens_in=intake_result.tokens_in,
            tokens_out=intake_result.tokens_out,
            source=req.source,
        )
    except Exception:
        pass

    if tool is None:
        # Pure conversation
        return {
            "session_id": session_id,
            "category": "CONVERSATION",
            "response": intake_result.response_text,
        }

    if tool == "mutate_org":
        result_text = await dispatch(intake_result)
        summary = intake_result.tool_input.get("action", "org change") if intake_result.tool_input else "org change"
        if req.source == "slack":
            notify(f"*Org Change:* {summary}\n\n{result_text}")
        return {
            "session_id": session_id,
            "category": "ORG_CHANGE",
            "summary": summary,
            "result": result_text,
            "org_summary": registry.get_org_summary(),
        }

    if tool in ("query_org", "query_status", "query_cost", "query_kpi", "query_ml"):
        result_text = await dispatch(intake_result)
        return {
            "session_id": session_id,
            "category": "QUERY",
            "tool": tool,
            "result": result_text,
        }

    if tool == "talk_to_agent":
        result_text = await dispatch(intake_result)
        agent_id = intake_result.tool_input.get("agent_id", "") if intake_result.tool_input else ""
        return {
            "session_id": session_id,
            "category": "AGENT_TALK",
            "agent": agent_id,
            "response": result_text,
        }

    if tool == "generate_document":
        # Handle document generation
        tool_input = intake_result.tool_input or {}
        doc_type = tool_input.get("document_type", "pdf")
        doc_desc = tool_input.get("description", req.message)
        from src.documents.generator import generate_document
        result = await generate_document(doc_desc, {"format": doc_type, "title": doc_desc[:100]})
        return {
            "session_id": session_id,
            "category": "DOCUMENT",
            "result": result,
        }

    if tool == "start_directive":
        # Engineering work — hand off to orchestrator
        directive_text = intake_result.tool_input.get("directive_text", req.message) if intake_result.tool_input else req.message

        sessions[session_id] = {
            "directive": directive_text,
            "source": req.source,
            "project_path": req.project_path,
            "status": "running",
            "state": None,
            "error": None,
        }

        task = asyncio.create_task(
            execute_directive_bg(session_id, directive_text, req.project_path, req.source)
        )
        active_runs[session_id] = task

        return {
            "session_id": session_id,
            "category": "DIRECTIVE",
            "summary": directive_text[:100],
            "status": "started",
            "message": f"Directive received. The org is working on it. Session: {session_id}",
        }

    # Fallback
    return {
        "session_id": session_id,
        "category": "UNKNOWN",
        "response": intake_result.response_text or "I didn't understand that request.",
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
            sessions.get(req.session_id or "", {}).get("project_path", os.path.expanduser("~/Projects")),
        )
    else:
        result = await run_planning_agent(agent_key, agent_config, req.message)

    return {
        "agent": agent.name,
        "agent_id": agent.id,
        "response": result.output,
        "cost": result.cost_usd,
        "model": result.model,
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
            return dict(org_data)
        result = (await status()).model_dump()
        result["category"] = "COMMAND"
        return dict(result)

    elif command == "org":
        org_data = await get_org()
        org_data["category"] = "COMMAND"
        return dict(org_data)

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
