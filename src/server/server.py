"""
NEXUS Server

FastAPI server running on localhost:4200. Single entry point for all clients.
Now with dynamic org management and CEO natural language interpretation.
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Literal

from src.agents.registry import registry
from src.agents.ceo_interpreter import execute_org_change
from src.agents.org_chart_generator import generate_org_chart, update_org_chart_in_repo
from src.agents.sdk_bridge import run_sdk_agent, run_planning_agent
from src.cost.tracker import cost_tracker
from src.slack.notifier import notify, notify_demo, notify_completion, notify_escalation, notify_kpi
from src.session.store import session_store
from src.kpi.tracker import kpi_tracker
from src.git_ops.git import GitOps
from src.security.scanner import run_full_audit


sessions: dict[str, dict] = {}
active_runs: dict[str, asyncio.Task] = {}


class MessageRequest(BaseModel):
    message: str
    source: Literal["slack", "ide", "cli", "api", "happy_coder"] = "api"
    project_path: str = ""
    session_id: str | None = None
    history: list[dict] = Field(default_factory=list)


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


async def execute_directive_bg(session_id: str, directive: str, project_path: str, source: str, project_id: str = ""):
    try:
        await session_store.create_session(session_id, directive, source, project_path)
        await session_store.add_message(session_id, "user", directive)

        from src.orchestrator.task_runner import run_task
        result = await run_task(session_id, directive, project_path, project_id)

        sessions[session_id]["state"] = result
        sessions[session_id]["status"] = result.get("status", "complete")
        await session_store.update_status(session_id, result.get("status", "complete"))

    except Exception as e:
        import traceback
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = str(e)
        await session_store.update_status(session_id, "error", str(e))
        print(f"[Server] Directive execution failed: {e}")
        print(f"[Server] Traceback:\n{traceback.format_exc()}")
        notify_escalation("orchestrator", f"Execution failed: {str(e)[:200]}")

    finally:
        if session_id in active_runs:
            del active_runs[session_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize persistent memory
    from src.memory.store import memory
    memory.init()

    # Initialize session persistence
    await session_store.init()

    if not registry.is_initialized():
        registry.load_from_yaml()
        notify("Nexus initialized from default org structure.")

    nexus_path = os.path.expanduser("~/Projects/nexus")
    if os.path.exists(nexus_path):
        update_org_chart_in_repo(nexus_path)

    notify("Nexus team is online.")

    # Fire off a Haiku greeting async
    try:
        import anthropic
        def _load_key(key_name):
            try:
                with open(os.path.expanduser("~/.nexus/.env.keys")) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(key_name + "="):
                            return line.split("=", 1)[1]
            except FileNotFoundError:
                pass
            return os.environ.get(key_name)

        api_key = _load_key("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=api_key)
        agents = registry.get_active_agents()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            system="You are Nexus, an AI engineering org that just came online. Write ONE short, witty sentence about being ready for work. Be casual and fun — like a team Slack message. No emojis. No markdown.",
            messages=[{"role": "user", "content": f"We have {len(agents)} agents online. Say something."}],
        )
        notify(resp.content[0].text)
    except Exception as e:
        print(f"[Server] Haiku greeting failed: {e}")

    # Resume any interrupted tasks from before restart
    from src.orchestrator.task_runner import resume_pending_tasks
    await resume_pending_tasks()

    yield
    # On shutdown, self-commit any pending changes
    if os.path.exists(os.path.join(nexus_path, ".git")):
        git = GitOps(nexus_path)
        if not git.status()["clean"]:
            git.self_commit("auto-save on shutdown")
    notify("Nexus server shutting down.")


app = FastAPI(
    title="NEXUS Server",
    description="Enterprise multi-agent orchestration system",
    version="0.3.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.3.0", "active_agents": len(registry.get_active_agents())}


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

    try:
        from src.agents.conversation import converse, resolve_project

        result = await converse(req.message, history=req.history)

        answer = result["answer"]
        actions = result.get("actions", [])

        # Process any actions
        for action in actions:
            if action["type"] == "execute":
                # Find the project and kick off execution
                project = resolve_project(action["name"])
                if project:
                    proj_path = os.path.expanduser(project.get("path", "~/Projects"))
                    directive = f"{project.get('description', action['name'])}"
                    project_id = project.get("id", "")

                    sessions[session_id] = {
                        "directive": directive,
                        "source": req.source,
                        "project_path": proj_path,
                        "status": "running",
                        "state": None,
                        "error": None,
                    }

                    task = asyncio.create_task(
                        execute_directive_bg(session_id, directive, proj_path, req.source, project_id)
                    )
                    active_runs[session_id] = task

            elif action["type"] == "org_change":
                try:
                    # Parse and execute org change
                    intent = {
                        "category": "ORG_CHANGE",
                        "sub_type": action["action"],
                        "details": json.loads(action["details"]) if isinstance(action["details"], str) else action["details"],
                    }
                    from src.agents.ceo_interpreter import execute_org_change
                    org_result = await execute_org_change(intent)
                    answer += f"\n\n{org_result}"
                except Exception as e:
                    answer += f"\n\nOrg change failed: {e}"

            elif action["type"] == "command":
                cmd_result = await run_command_internal(action["name"], action.get("args", ""), req.source)
                if "dashboard" in cmd_result:
                    answer += f"\n```{cmd_result['dashboard']}```"
                elif "reporting_tree" in cmd_result:
                    answer += f"\n```{cmd_result['reporting_tree']}```"

        return {
            "session_id": session_id,
            "category": "CONVERSATION",
            "answer": answer,
            "actions": [a["type"] for a in actions],
            "cost": result.get("cost", 0),
        }

    except Exception as e:
        import traceback
        print(f"[Server] Message handler error: {e}")
        print(f"[Server] Traceback:\n{traceback.format_exc()}")
        return {
            "session_id": session_id,
            "category": "ERROR",
            "error": f"{type(e).__name__}: {str(e)[:300]}",
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
    # Check in-memory first, fall back to persistent store
    if session_id in sessions:
        return sessions[session_id]
    persisted = await session_store.get_session(session_id)
    if persisted:
        return persisted
    return {"error": "Session not found"}


@app.get("/sessions")
async def get_sessions():
    """Get recent session history from persistent store."""
    return {"sessions": await session_store.get_recent_sessions(20)}


@app.get("/kpi")
async def get_kpi():
    """Get KPI dashboard data."""
    summary = kpi_tracker.get_summary(24)
    dashboard = kpi_tracker.generate_dashboard(24)
    return {"summary": summary, "dashboard": dashboard}


@app.get("/cost")
async def get_cost():
    """Get full CFO cost report."""
    return {
        "session_cost": cost_tracker.total_cost,
        "hourly_rate": cost_tracker.hourly_rate,
        "monthly_cost": cost_tracker.get_monthly_cost(),
        "over_budget": cost_tracker.over_budget,
        "by_model": cost_tracker.by_model,
        "by_agent": cost_tracker.by_agent,
        "by_project": cost_tracker.by_project,
        "daily_breakdown": cost_tracker.get_daily_breakdown(7),
        "report": cost_tracker.generate_cfo_report(),
    }


@app.post("/security/scan")
async def security_scan(project_path: str = os.path.expanduser("~/Projects/nexus")):
    """Run full security audit on a project."""
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_full_audit, project_path)
    return result


async def run_command_internal(command: str, args: str, source: str) -> dict:
    if command == "kpi":
        dashboard = kpi_tracker.generate_dashboard(24)
        if source == "slack":
            notify_kpi(dashboard)
        return {"category": "COMMAND", "command": "kpi", "dashboard": dashboard}

    elif command == "cost":
        report = cost_tracker.generate_cfo_report()
        return {
            "category": "COMMAND",
            "command": "cost",
            "total_cost": cost_tracker.total_cost,
            "hourly_rate": cost_tracker.hourly_rate,
            "by_model": cost_tracker.by_model,
            "by_agent": cost_tracker.by_agent,
            "over_budget": cost_tracker.over_budget,
            "monthly_cost": cost_tracker.get_monthly_cost(),
            "dashboard": report,
        }

    elif command == "security":
        project_path = args or os.path.expanduser("~/Projects/nexus")
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_full_audit, project_path)
        if source == "slack":
            notify(f"```{result['summary']}```")
        return {
            "category": "COMMAND",
            "command": "security",
            **result,
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


def start_server(host: str = "127.0.0.1", port: int = 4200):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
