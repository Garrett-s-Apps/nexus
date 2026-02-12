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
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from src.agents.org_chart import get_org_summary
from src.memory.store import memory
from src.observability.api_routes import router as metrics_router
from src.security.jwt_auth import sign_response


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


app = FastAPI(title="NEXUS", version="3.0.0", lifespan=lifespan)
app.include_router(metrics_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def jwt_signing_middleware(request: Request, call_next):
    """Attach an integrity JWT to every JSON response."""
    response = await call_next(request)

    # Only sign JSON responses (skip SSE, HTML, file downloads)
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return response

    # Read the body, sign it, attach header, then re-emit
    body_chunks = []
    async for chunk in response.body_iterator:
        body_chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
    body = b"".join(body_chunks)

    try:
        import json as _json
        data = _json.loads(body)
        token = sign_response(data)
        response.headers["X-Nexus-JWT"] = token
    except Exception:
        pass  # Non-JSON or signing failure — pass through unsigned

    from starlette.responses import Response as StarletteResponse
    return StarletteResponse(
        content=body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
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
    from src.resilience.health_monitor import health_monitor
    return {
        "status": "ok", "engine_running": engine.running,
        "agents": len(memory.get_all_agents()),
        "active_directive": memory.get_active_directive() is not None,
        "working_agents": len(memory.get_working_agents()),
        "resilience": health_monitor.status(),
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
async def serve_dashboard():
    import os
    dashboard_path = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")
    dashboard_path = os.path.normpath(dashboard_path)
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path, media_type="text/html")
    return {"error": "Dashboard not found", "path": dashboard_path}


@app.get("/dashboard/logo.svg")
async def serve_logo():
    import os
    logo_path = os.path.join(os.path.dirname(__file__), "..", "dashboard", "logo.svg")
    logo_path = os.path.normpath(logo_path)
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/svg+xml")
    return {"error": "Logo not found"}
