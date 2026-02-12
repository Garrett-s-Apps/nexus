"""
NEXUS Server (v1)

FastAPI on localhost:4200.
- POST /message — messages from Garrett
- GET /events — SSE stream for dashboard
- GET /state — world state snapshot
- GET /agents, /org, /directive, /services, /health, /cost
"""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agents.org_chart import get_org_summary
from src.memory.store import memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Server] Initializing...")
    memory.init()
    memory.emit_event("server", "starting", {})

    from src.orchestrator.engine import engine
    await engine.start()

    asyncio.create_task(_start_slack())

    print("[Server] NEXUS v1 running on http://localhost:4200")
    memory.emit_event("server", "ready", {"port": 4200})
    yield

    print("[Server] Shutting down...")
    from src.orchestrator.engine import engine as eng
    await eng.stop()
    memory.emit_event("server", "stopped", {})


async def _start_slack():
    try:
        from src.slack.listener import start_slack_listener
        await start_slack_listener()
    except Exception as e:
        print(f"[Server] Slack failed (non-fatal): {e}")


app = FastAPI(title="NEXUS", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


class MessageRequest(BaseModel):
    message: str
    source: str = "api"


@app.post("/message")
async def handle_message(req: MessageRequest):
    from src.orchestrator.engine import engine
    response = await engine.handle_message(req.message, req.source)
    return {"response": response}


@app.get("/events")
async def event_stream(request: Request, last_id: int = 0):
    async def generate():
        current_id = last_id
        while True:
            if await request.is_disconnected():
                break
            events = memory.get_events_since(current_id, limit=50)
            for event in events:
                current_id = event["id"]
                data = json.dumps({
                    "id": event["id"], "timestamp": event["timestamp"],
                    "source": event["source"], "type": event["event_type"],
                    "data": json.loads(event["data"]) if isinstance(event["data"], str) else event["data"],
                })
                yield f"id: {event['id']}\nevent: {event['event_type']}\ndata: {data}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/state")
async def get_state():
    return memory.get_world_snapshot()


@app.get("/agents")
async def get_agents():
    agents = memory.get_all_agents()
    return {"agents": agents, "count": len(agents)}


@app.get("/org")
async def get_org():
    return {"org": get_org_summary()}


@app.get("/directive")
async def get_directive():
    directive = memory.get_active_directive()
    if not directive:
        return {"directive": None, "task_board": [], "context": []}
    return {
        "directive": directive,
        "task_board": memory.get_board_tasks(directive["id"]),
        "context": memory.get_context_for_directive(directive["id"], limit=20),
    }


@app.get("/services")
async def get_services():
    return {"services": memory.get_all_services()}


@app.get("/health")
async def health():
    from src.orchestrator.engine import engine
    return {
        "status": "ok", "engine_running": engine.running,
        "agents": len(memory.get_all_agents()),
        "active_directive": memory.get_active_directive() is not None,
        "working_agents": len(memory.get_working_agents()),
    }


@app.get("/cost")
async def get_cost():
    try:
        from src.cost.tracker import cost_tracker
        return cost_tracker.get_summary()
    except Exception:
        return {"total": 0, "note": "Cost tracker not available"}


@app.get("/status")
async def legacy_status():
    return await get_state()


@app.get("/dashboard")
async def legacy_dashboard():
    state = memory.get_world_snapshot()
    directive = state.get("directive")
    agents = state.get("agents", [])
    lines = ["NEXUS v1.0", "=" * 40]
    if directive:
        lines.append(f"Directive: {directive['text'][:80]}")
        lines.append(f"Status: {directive['status']}")
    else:
        lines.append("Standing by.")
    working = [a for a in agents if a["status"] in ("working", "thinking")]
    lines.append(f"\nAgents: {len(working)} working, {len(agents) - len(working)} idle")
    for a in working:
        lines.append(f"  [{a['status']}] {a['name']}: {a['last_action'][:50]}")
    return {"dashboard": "\n".join(lines)}
