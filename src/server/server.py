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
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

logger = logging.getLogger("nexus.server")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from src.agents.org_chart import get_org_summary
from src.memory.store import memory
from src.observability.api_routes import router as metrics_router
from src.security.auth_gate import (
    AUTH_COOKIE,
    SESSION_TTL,
    create_session,
    invalidate_session,
    verify_passphrase,
    verify_session,
)
from src.security.jwt_auth import sign_response


def _register_background_jobs():
    """Register all periodic background jobs with the scheduler."""
    from src.observability.background import scheduler

    # ML retraining — checks threshold, runs only when enough outcomes
    def _retrain():
        from src.ml.feedback import do_retrain
        do_retrain()

    scheduler.register("ml_retrain", _retrain, interval_seconds=3600)

    # RAG chunk pruning — remove old knowledge chunks
    def _rag_prune():
        from src.ml.knowledge_store import knowledge_store
        knowledge_store.prune_old_chunks()

    scheduler.register("rag_prune", _rag_prune, interval_seconds=300)

    # Dedup table cleanup — remove old processed message entries
    def _dedup_cleanup():
        memory.cleanup_old_processed(max_age_hours=24)

    scheduler.register("dedup_cleanup", _dedup_cleanup, interval_seconds=3600)

    # Embedding warmup — run once at startup to avoid cold-start penalty
    def _embedding_warmup():
        from src.ml.embeddings import encode
        encode("warmup")

    scheduler.register("embedding_warmup", _embedding_warmup, interval_seconds=86400, run_immediately=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing...")
    memory.init()
    memory.emit_event("server", "starting", {})

    from src.orchestrator.engine import engine
    await engine.start()

    # Start background scheduler with periodic jobs
    from src.observability.background import scheduler
    _register_background_jobs()
    await scheduler.start()

    asyncio.create_task(_start_slack())

    logger.info("NEXUS v1 running on http://localhost:4200")
    memory.emit_event("server", "ready", {"port": 4200})
    yield

    logger.info("Shutting down...")
    from src.observability.background import scheduler as bg
    await bg.stop()
    from src.orchestrator.engine import engine as eng
    await eng.stop()
    memory.emit_event("server", "stopped", {})


async def _start_slack():
    try:
        from src.slack.listener import start_slack_listener
        await start_slack_listener()
    except Exception as e:
        logger.warning("Slack failed (non-fatal): %s", e)


app = FastAPI(title="NEXUS", version="3.0.0", lifespan=lifespan)
app.include_router(metrics_router)

_ALLOWED_ORIGINS = [
    "http://localhost:4200",
    "http://localhost:4201",
    "http://127.0.0.1:4200",
    "http://127.0.0.1:4201",
    "https://nexus-dashboard-black-nine.vercel.app",
]


def _origin_allowed(origin: str) -> bool:
    """Allow listed origins plus any *.trycloudflare.com tunnel."""
    return origin in _ALLOWED_ORIGINS or (
        origin.endswith(".trycloudflare.com") and origin.startswith("https://")
    )


app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.trycloudflare\.com",
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Nexus-JWT"],
)


@app.middleware("http")
async def jwt_signing_middleware(request: Request, call_next):
    """Attach an integrity JWT to every JSON response."""
    response = await call_next(request)

    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return response

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
        pass

    from starlette.responses import Response as StarletteResponse
    return StarletteResponse(
        content=body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )



_PUBLIC_PATHS = {
    "/auth/login", "/auth/check", "/health", "/dashboard/logo.svg",
}
_PUBLIC_PREFIXES = ("/auth/",)
_TOKEN_HEADER = "Authorization"  # noqa: S105 — header name, not a password


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting reverse-proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return str(forwarded.split(",")[0].strip())
    return request.client.host if request.client else "127.0.0.1"


@app.middleware("http")
async def auth_gate_middleware(request: Request, call_next):
    """Reject unauthenticated requests to protected routes."""
    path = request.url.path

    if path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)

    if path == "/dashboard" or path == "/":
        return await call_next(request)

    # Check cookie first, then Authorization: Bearer header (for cross-origin)
    session_id = request.cookies.get(AUTH_COOKIE)
    if not session_id:
        auth_header = request.headers.get(_TOKEN_HEADER, "")
        if auth_header.startswith("Bearer "):
            session_id = auth_header[7:]

    user_agent = request.headers.get("user-agent", "")
    client_ip = _get_client_ip(request)

    if not verify_session(session_id, user_agent=user_agent, client_ip=client_ip):
        from starlette.responses import JSONResponse
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return await call_next(request)


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

# Rate limiting for login attempts
_login_attempts: dict[str, list[float]] = {}
_MAX_LOGIN_ATTEMPTS = 5
_RATE_LIMIT_WINDOW = 60  # seconds


def _cleanup_old_attempts():
    """Remove attempts older than the rate limit window."""
    import time
    cutoff = time.time() - _RATE_LIMIT_WINDOW
    for ip in list(_login_attempts.keys()):
        _login_attempts[ip] = [ts for ts in _login_attempts[ip] if ts > cutoff]
        if not _login_attempts[ip]:
            del _login_attempts[ip]


def _check_rate_limit(ip: str) -> bool:
    """Check if IP has exceeded rate limit. Returns True if allowed, False if rate limited."""
    import time
    _cleanup_old_attempts()

    attempts = _login_attempts.get(ip, [])
    if len(attempts) >= _MAX_LOGIN_ATTEMPTS:
        return False

    _login_attempts.setdefault(ip, []).append(time.time())
    return True


def _clear_rate_limits():
    """Clear all rate limit tracking. Used for testing."""
    global _login_attempts
    _login_attempts = {}


class LoginRequest(BaseModel):
    passphrase: str


@app.post("/auth/login")
async def auth_login(req: LoginRequest, request: Request):
    """Verify passphrase and set httponly session cookie."""
    client_ip = _get_client_ip(request)

    if not _check_rate_limit(client_ip):
        from starlette.responses import JSONResponse
        return JSONResponse(
            {"error": "too many attempts, try again later"},
            status_code=429
        )

    if not verify_passphrase(req.passphrase):
        from starlette.responses import JSONResponse
        return JSONResponse({"error": "invalid passphrase"}, status_code=403)

    user_agent = request.headers.get("user-agent", "")
    session_id = create_session(user_agent=user_agent, client_ip=client_ip)

    from starlette.responses import JSONResponse
    resp = JSONResponse({"ok": True, "token": session_id})
    resp.set_cookie(
        AUTH_COOKIE,
        session_id,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="strict",
        secure=os.environ.get("NEXUS_ENV") != "development",
        path="/",
    )
    return resp


@app.get("/auth/check")
async def auth_check(request: Request):
    """Let the dashboard check if the current session is valid."""
    session_id = request.cookies.get(AUTH_COOKIE)
    user_agent = request.headers.get("user-agent", "")
    client_ip = _get_client_ip(request)
    valid = verify_session(session_id, user_agent=user_agent, client_ip=client_ip)
    return {"authenticated": valid}


@app.post("/auth/logout")
async def auth_logout(request: Request):
    """Destroy the session and clear the cookie."""
    session_id = request.cookies.get(AUTH_COOKIE)
    if session_id:
        invalidate_session(session_id)
    from starlette.responses import JSONResponse
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(AUTH_COOKIE, path="/")
    return resp


class MessageRequest(BaseModel):
    message: str
    source: str = "api"


@app.post("/message")
async def handle_message(req: MessageRequest):
    from src.orchestrator.engine import engine
    response = await engine.handle_message(req.message, req.source)
    return {"response": response}


@app.get("/events")
async def event_stream(request: Request, last_id: int = 0, token: str = ""):
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
                yield f"id: {event['id']}\ndata: {data}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/state")
async def get_state():
    snapshot = memory.get_world_snapshot()
    snapshot["latest_event_id"] = memory.get_latest_event_id()
    return snapshot


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
    from datetime import UTC, datetime

    from starlette.responses import JSONResponse

    checks: dict[str, dict] = {}
    overall = "healthy"
    engine_running = False

    # Database connectivity — degrade gracefully, never return 503
    try:
        from src.agents.registry import registry
        from src.cost.tracker import cost_tracker
        from src.ml.knowledge_store import knowledge_store
        from src.ml.store import ml_store

        for name, check_fn in [
            ("ml_db", lambda: ml_store._conn is not None),
            ("knowledge_db", lambda: knowledge_store._conn is not None),
            ("memory_db", lambda: memory._conn is not None),
            ("registry_db", lambda: os.path.exists(registry.db_path)),
            ("cost_db", lambda: os.path.exists(cost_tracker.db_path)),
        ]:
            try:
                checks[name] = {"status": "up" if check_fn() else "down"}
                if not check_fn():
                    overall = "degraded"
            except Exception as e:
                checks[name] = {"status": "down", "error": str(e)}
                overall = "degraded"
    except Exception as e:
        checks["databases"] = {"status": "unknown", "error": str(e)}
        overall = "degraded"

    # ML model staleness
    try:
        from src.ml.feedback import get_learning_status
        learning = get_learning_status()
        checks["ml_models"] = {
            "status": "up",
            "training_data_count": learning.get("training_data_count", 0),
            "models_trained": learning.get("models_trained", False),
        }
    except Exception as e:
        checks["ml_models"] = {"status": "degraded", "error": str(e)}
        if overall == "healthy":
            overall = "degraded"

    # RAG index health
    try:
        from src.ml.knowledge_store import knowledge_store as ks
        chunk_count_dict: dict = ks.count_chunks()
        total_chunks = sum(chunk_count_dict.values())
        checks["rag_index"] = {
            "status": "up",
            "chunk_count": total_chunks,
        }
    except Exception as e:
        checks["rag_index"] = {"status": "degraded", "error": str(e)}
        if overall == "healthy":
            overall = "degraded"

    # Circuit breaker summary
    try:
        from src.agents.registry import registry as reg
        agents = reg.get_active_agents()
        circuit_summary = {"closed": 0, "open": 0, "half_open": 0}
        for agent in agents:
            state = agent.metadata.get("circuit_state", "closed")
            if state in circuit_summary:
                circuit_summary[state] += 1
        checks["circuit_breakers"] = {
            "status": "up" if circuit_summary["open"] == 0 else "degraded",
            **circuit_summary,
        }
    except Exception as e:
        checks["circuit_breakers"] = {"status": "unknown", "error": str(e)}

    # Background scheduler
    try:
        from src.observability.background import scheduler
        sched_status = scheduler.status()
        running = scheduler._running
        checks["scheduler"] = {
            "status": "up" if running else "down",
            "jobs": sched_status,
        }
    except Exception as e:
        checks["scheduler"] = {"status": "unknown", "error": str(e)}

    # Engine status
    try:
        from src.orchestrator.engine import engine as eng
        engine_running = getattr(eng, "running", False)
    except Exception:
        engine_running = False

    return JSONResponse(
        {
            "status": "ok" if overall != "unhealthy" else "degraded",
            "engine_running": engine_running,
            "checks": checks,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        status_code=200,
    )


@app.get("/health/detail")
async def health_detail():
    """Detailed health check with per-subsystem diagnostics."""
    from datetime import datetime

    from starlette.responses import JSONResponse

    from src.agents.registry import registry
    from src.cost.tracker import cost_tracker
    from src.ml.knowledge_store import knowledge_store
    from src.ml.store import ml_store
    from src.observability.background import scheduler

    checks: dict[str, dict] = {}
    overall = "healthy"

    # Database connectivity (same as /health)
    for name, check_fn in [
        ("ml_db", lambda: ml_store._conn is not None),
        ("knowledge_db", lambda: knowledge_store._conn is not None),
        ("memory_db", lambda: memory._conn is not None),
        ("registry_db", lambda: os.path.exists(registry.db_path)),
        ("cost_db", lambda: os.path.exists(cost_tracker.db_path)),
    ]:
        try:
            checks[name] = {"status": "up" if check_fn() else "down"}
            if not check_fn():
                overall = "degraded"
        except Exception as e:
            checks[name] = {"status": "down", "error": str(e)}
            overall = "unhealthy"

    # ML model staleness with detailed metrics
    try:
        from src.ml.feedback import get_learning_status
        learning = get_learning_status()

        # Get pending outcomes count
        pending_outcomes = 0
        try:
            c = ml_store._db.cursor()
            pending_outcomes = c.execute(
                "SELECT COUNT(*) FROM task_outcomes WHERE created_at > (SELECT COALESCE(MAX(trained_at), 0) FROM model_artifacts)"
            ).fetchone()[0]
        except Exception:
            pass

        checks["ml_models"] = {
            "status": "up",
            "training_data_count": learning.get("training_data_count", 0),
            "models_trained": learning.get("models_trained", False),
            "pending_outcomes": pending_outcomes,
            "router_status": learning.get("router", {}),
            "predictor_status": learning.get("predictor", {}),
        }
    except Exception as e:
        checks["ml_models"] = {"status": "degraded", "error": str(e)}
        if overall == "healthy":
            overall = "degraded"

    # RAG index health with chunk breakdown
    try:
        chunk_count_dict: dict = knowledge_store.count_chunks()
        total_chunks = sum(chunk_count_dict.values())
        checks["rag_index"] = {
            "status": "up",
            "chunk_count": total_chunks,
            "chunks_by_type": chunk_count_dict,
        }
    except Exception as e:
        checks["rag_index"] = {"status": "degraded", "error": str(e)}
        if overall == "healthy":
            overall = "degraded"

    # Circuit breaker summary with agent details
    try:
        agents = registry.get_active_agents()
        circuit_summary = {"closed": 0, "open": 0, "half_open": 0}
        circuit_details = []
        for agent in agents:
            state = agent.metadata.get("circuit_state", "closed")
            if state in circuit_summary:
                circuit_summary[state] += 1
            if state != "closed":
                circuit_details.append({
                    "agent_id": agent.id,
                    "state": state,
                    "failure_count": agent.metadata.get("failure_count", 0),
                })
        checks["circuit_breakers"] = {
            "status": "up" if circuit_summary["open"] == 0 else "degraded",
            **circuit_summary,
            "details": circuit_details,
        }
    except Exception as e:
        checks["circuit_breakers"] = {"status": "unknown", "error": str(e)}

    # Background scheduler with job details
    try:
        sched_status = scheduler.status()
        running = scheduler._running
        checks["scheduler"] = {
            "status": "up" if running else "down",
            "running": running,
            "job_count": len(sched_status),
            "jobs": sched_status,
        }
    except Exception as e:
        checks["scheduler"] = {"status": "unknown", "error": str(e)}

    # Engine status
    try:
        from src.orchestrator.engine import engine
        checks["engine"] = {
            "status": "up" if engine.running else "down",
            "running": engine.running,
        }
    except Exception as e:
        checks["engine"] = {"status": "unknown", "error": str(e)}

    # Resilience monitor
    try:
        from src.resilience.health_monitor import health_monitor
        checks["resilience"] = {
            "status": "up",
            **health_monitor.status(),
        }
    except Exception as e:
        checks["resilience"] = {"status": "unknown", "error": str(e)}

    status_code = 200 if overall != "unhealthy" else 503
    return JSONResponse(
        {"status": overall, "checks": checks, "timestamp": datetime.utcnow().isoformat()},
        status_code=status_code,
    )


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


# ---------------------------------------------------------------------------
# CLI Session Management
# ---------------------------------------------------------------------------

@app.get("/sessions")
async def list_sessions():
    """List all active Claude Code CLI sessions."""
    from src.sessions.cli_pool import cli_pool
    return cli_pool.status()


@app.delete("/sessions/{thread_ts}")
async def kill_session(thread_ts: str):
    """Terminate a specific CLI session by thread_ts."""
    from src.sessions.cli_pool import cli_pool
    session = cli_pool._sessions.get(thread_ts)
    if not session:
        return {"error": "Session not found", "thread_ts": thread_ts}
    await session.kill()
    del cli_pool._sessions[thread_ts]
    return {"ok": True, "thread_ts": thread_ts}


@app.delete("/sessions")
async def kill_all_sessions():
    """Terminate all CLI sessions."""
    from src.sessions.cli_pool import cli_pool
    count = cli_pool.active_count()
    await cli_pool.shutdown()
    return {"ok": True, "killed": count}


@app.get("/dashboard")
async def serve_dashboard():
    import os
    dashboard_path = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")
    dashboard_path = os.path.normpath(dashboard_path)
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path, media_type="text/html")
    return {"error": "Dashboard not found", "path": dashboard_path}


@app.get("/chat/threads")
async def list_threads():
    """List recent Slack threads (directives and conversations)."""
    from src.slack.listener import get_channel_id, get_slack_client
    client = get_slack_client()
    channel = get_channel_id()
    if not client or not channel:
        return {"threads": [], "error": "Slack not connected"}

    try:
        result = await client.conversations_history(channel=channel, limit=30)
        threads = []
        for msg in result.get("messages", []):
            if msg.get("reply_count", 0) > 0 or msg.get("subtype") is None:
                threads.append({
                    "thread_ts": msg.get("thread_ts") or msg.get("ts"),
                    "text": msg.get("text", "")[:200],
                    "user": msg.get("user", ""),
                    "reply_count": msg.get("reply_count", 0),
                    "ts": msg.get("ts"),
                })
        return {"threads": threads}
    except Exception as e:
        return {"threads": [], "error": str(e)}


@app.get("/chat/thread/{thread_ts}")
async def get_thread(thread_ts: str):
    """Get all messages in a Slack thread."""
    from src.slack.listener import get_channel_id, get_slack_client
    client = get_slack_client()
    channel = get_channel_id()
    if not client or not channel:
        return {"messages": [], "error": "Slack not connected"}

    try:
        result = await client.conversations_replies(channel=channel, ts=thread_ts, limit=100)
        raw_msgs: list[dict] = result.get("messages", [])  # type: ignore[assignment]
        messages = [
            {
                "ts": msg.get("ts"),
                "user": msg.get("user", "bot"),
                "text": msg.get("text", ""),
                "is_bot": msg.get("bot_id") is not None,
            }
            for msg in raw_msgs
        ]
        return {"messages": messages, "thread_ts": thread_ts}
    except Exception as e:
        return {"messages": [], "error": str(e)}


@app.post("/chat/send")
async def send_chat(req: MessageRequest):
    """Send a message through the engine (creates or continues a thread)."""
    from src.orchestrator.engine import engine
    response = await engine.handle_message(req.message, source="dashboard")
    return {"response": response}


@app.get("/dashboard/logo.svg")
async def serve_logo():
    import os
    logo_path = os.path.join(os.path.dirname(__file__), "..", "dashboard", "logo.svg")
    logo_path = os.path.normpath(logo_path)
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/svg+xml")
    return {"error": "Logo not found"}


# === ML Learning Endpoints ===

@app.get("/ml/status")
async def ml_status():
    """Get ML learning system status — models, training data, readiness."""
    from src.ml.feedback import get_learning_status
    return get_learning_status()


@app.post("/ml/train")
async def ml_train():
    """Force retrain all ML models."""
    from src.ml.predictor import train_all
    from src.ml.router import train
    return {
        "router": train(force=True),
        "predictors": train_all(force=True),
    }


@app.post("/ml/similar")
async def ml_similar(req: MessageRequest):
    """Find similar past directives for a given text."""
    from src.ml.similarity import analyze_new_directive
    return analyze_new_directive(req.message)


@app.get("/ml/agent/{agent_id}/stats")
async def ml_agent_stats(agent_id: str):
    """Get ML-derived performance stats for an agent."""
    from src.agents.registry import registry
    from src.ml.store import ml_store
    return {
        "success_rate": ml_store.get_agent_success_rate(agent_id),
        "reliability": registry.get_agent_reliability(agent_id),
    }
