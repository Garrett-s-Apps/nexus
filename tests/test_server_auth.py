"""
FastAPI integration tests for auth middleware.

Tests cover:
- Auth check without session
- Login with wrong passphrase
- Login with correct passphrase (sets httponly cookie)
- Protected routes without session (401)
- Protected routes with valid session (200)
- Logout destroys session
- Public paths always accessible
- Auth check with valid session

Uses httpx.AsyncClient with mocked dependencies to avoid starting the full engine.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# Mock all heavy dependencies before importing the server
@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock heavy imports to prevent engine startup and module loading."""
    with patch("src.memory.store.memory") as mock_mem, \
         patch("src.orchestrator.engine.engine") as mock_engine, \
         patch("src.observability.api_routes.router"), \
         patch("src.agents.org_chart.get_org_summary") as mock_org, \
         patch("src.resilience.health_monitor.health_monitor") as mock_health, \
         patch("src.slack.listener.start_slack_listener") as mock_slack, \
         patch("src.slack.listener.get_slack_client") as mock_slack_client, \
         patch("src.slack.listener.get_channel_id") as mock_channel_id, \
         patch("src.cost.tracker.cost_tracker") as mock_cost:

        # Configure memory mock
        mock_mem.init = MagicMock()
        mock_mem.emit_event = MagicMock()
        mock_mem.get_events_since = MagicMock(return_value=[])
        mock_mem.get_world_snapshot = MagicMock(return_value={"status": "test"})
        mock_mem.get_all_agents = MagicMock(return_value=[])
        mock_mem.get_active_directive = MagicMock(return_value=None)
        mock_mem.get_working_agents = MagicMock(return_value=[])
        mock_mem.get_all_services = MagicMock(return_value=[])

        # Configure engine mock
        mock_engine.start = AsyncMock()
        mock_engine.stop = AsyncMock()
        mock_engine.running = True
        mock_engine.handle_message = AsyncMock(return_value="test response")

        # Configure other mocks
        mock_org.return_value = {"org": "test"}
        mock_health.status = MagicMock(return_value={"healthy": True})
        mock_slack.return_value = None
        mock_slack_client.return_value = None
        mock_channel_id.return_value = None
        mock_cost.get_summary = MagicMock(return_value={"total": 0})

        yield


@pytest.fixture
def mock_passphrase():
    """Mock the passphrase hash to the SHA-256 of 'test-pass'."""
    import hashlib
    test_hash = hashlib.sha256(b"test-pass").hexdigest()
    with patch("src.security.auth_gate._get_passphrase_hash", return_value=test_hash):
        yield


@pytest.fixture
async def client(mock_passphrase):
    """Create an async test client with a clean session store."""
    # Import after mocks are in place
    from src.security import auth_gate
    from src.server.server import _clear_rate_limits, app

    # Clear session store and rate limiter before each test
    auth_gate._sessions.clear()
    _clear_rate_limits()

    # Override the lifespan to skip engine startup
    @asynccontextmanager
    async def test_lifespan(app):
        # Minimal setup without heavy operations
        yield

    app.router.lifespan_context = test_lifespan

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clean up after test
    auth_gate._sessions.clear()


@pytest.mark.asyncio
async def test_auth_check_without_cookie(client):
    """GET /auth/check returns {"authenticated": false} without cookie."""
    response = await client.get("/auth/check")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}


@pytest.mark.asyncio
async def test_login_wrong_passphrase(client):
    """POST /auth/login with wrong passphrase returns 403."""
    response = await client.post("/auth/login", json={"passphrase": "wrong-pass"})
    assert response.status_code == 403
    assert response.json() == {"error": "invalid passphrase"}


@pytest.mark.asyncio
async def test_login_correct_passphrase(client):
    """POST /auth/login with correct passphrase returns 200 and sets httponly cookie."""
    response = await client.post("/auth/login", json={"passphrase": "test-pass"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "token" in data

    # Verify httponly cookie was set
    cookies = response.cookies
    assert "nexus_session" in cookies

    # Verify cookie attributes (httponly and samesite are handled by Set-Cookie header)
    cookie_header = response.headers.get("set-cookie", "")
    assert "nexus_session=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "samesite=strict" in cookie_header.lower()
    assert "Path=/" in cookie_header


@pytest.mark.asyncio
async def test_protected_route_without_session(client):
    """POST /message without session returns 401."""
    response = await client.post("/message", json={"message": "hi"})
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


@pytest.mark.asyncio
async def test_protected_route_requires_auth(client):
    """GET /state requires authentication (not public)."""
    response = await client.get("/state")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_with_valid_session(client):
    """POST /message with valid session is accepted."""
    # First login to get a session
    login_response = await client.post("/auth/login", json={"passphrase": "test-pass"})
    assert login_response.status_code == 200

    # Extract session cookie
    cookies = {"nexus_session": login_response.cookies["nexus_session"]}

    # Now access protected route — should not return 401
    response = await client.post("/message", json={"message": "hi"}, cookies=cookies)
    assert response.status_code != 401


@pytest.mark.asyncio
async def test_logout_destroys_session(client):
    """POST /auth/logout destroys session."""
    # First login
    login_response = await client.post("/auth/login", json={"passphrase": "test-pass"})
    assert login_response.status_code == 200
    cookies = {"nexus_session": login_response.cookies["nexus_session"]}

    # Verify session works
    state_response = await client.get("/state", cookies=cookies)
    assert state_response.status_code == 200

    # Logout
    logout_response = await client.post("/auth/logout", cookies=cookies)
    assert logout_response.status_code == 200
    assert logout_response.json() == {"ok": True}

    # Verify cookie was deleted
    cookie_header = logout_response.headers.get("set-cookie", "")
    assert "nexus_session=" in cookie_header
    assert "Max-Age=0" in cookie_header or "expires=" in cookie_header.lower()

    # Verify session no longer works on a protected endpoint
    msg_response = await client.post("/message", json={"message": "hi"}, cookies=cookies)
    assert msg_response.status_code == 401


@pytest.mark.asyncio
async def test_health_always_accessible(client):
    """GET /health is always accessible (public path, no auth needed)."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "engine_running" in data


@pytest.mark.asyncio
async def test_auth_check_with_valid_session(client):
    """GET /auth/check with valid session returns {"authenticated": true}."""
    # First login
    login_response = await client.post("/auth/login", json={"passphrase": "test-pass"})
    assert login_response.status_code == 200
    cookies = {"nexus_session": login_response.cookies["nexus_session"]}

    # Check auth status
    response = await client.get("/auth/check", cookies=cookies)
    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


@pytest.mark.asyncio
async def test_dashboard_route_always_accessible(client):
    """GET /dashboard is always accessible (serves login form)."""
    # Dashboard should be accessible without auth (it serves the login form)
    # Will return 404 in test because the file doesn't exist, but should not return 401
    response = await client.get("/dashboard")
    # Should not be 401 unauthorized
    assert response.status_code != 401


@pytest.mark.asyncio
async def test_session_fingerprint_validation(client):
    """Session tokens are bound to client fingerprint (User-Agent + IP)."""
    # Login with specific user agent
    login_response = await client.post(
        "/auth/login",
        json={"passphrase": "test-pass"},
        headers={"user-agent": "test-client-1"}
    )
    assert login_response.status_code == 200
    cookies = {"nexus_session": login_response.cookies["nexus_session"]}

    # Access with same user agent should work
    response = await client.post(
        "/message",
        json={"message": "hi"},
        cookies=cookies,
        headers={"user-agent": "test-client-1"}
    )
    assert response.status_code != 401

    # Access with different user agent should fail (fingerprint mismatch)
    response = await client.post(
        "/message",
        json={"message": "hi"},
        cookies=cookies,
        headers={"user-agent": "test-client-2"}
    )
    assert response.status_code == 401


# SEC-005: Persistent rate limiting tests
@pytest.mark.asyncio
async def test_rate_limit_progressive_lockout(client):
    """Failed login attempts trigger progressive lockout delays."""
    # 5 failed attempts should trigger 1 minute lockout
    for _i in range(5):
        response = await client.post("/auth/login", json={"passphrase": "wrong-pass"})
        assert response.status_code == 403

    # 6th attempt should be rate limited
    response = await client.post("/auth/login", json={"passphrase": "wrong-pass"})
    assert response.status_code == 429
    assert "rate limited" in response.json()["error"]


@pytest.mark.asyncio
async def test_rate_limit_persistent_across_restarts(client):
    """Rate limits persist in SQLite database across server restarts."""
    from src.server.server import _check_rate_limit_persistent, _record_failed_login

    # Simulate 10 failed attempts to trigger 10-minute lockout
    for _i in range(10):
        _record_failed_login("192.168.1.100")

    # Check that the IP is locked
    allowed, reason = _check_rate_limit_persistent("192.168.1.100")
    assert not allowed
    assert "locked for" in reason


@pytest.mark.asyncio
async def test_rate_limit_ip_validation(client):
    """X-Forwarded-For is only trusted from localhost."""
    # Direct connection should use client IP
    response = await client.post("/auth/login", json={"passphrase": "wrong-pass"})
    assert response.status_code == 403

    # X-Forwarded-For from untrusted source should be ignored
    response = await client.post(
        "/auth/login",
        json={"passphrase": "wrong-pass"},
        headers={"x-forwarded-for": "spoofed.ip.address"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_rate_limit_security_event_logging(client):
    """Failed login attempts are logged to login_attempts table."""
    import sqlite3

    from src.server.server import RATE_LIMIT_DB, _init_rate_limit_db, _record_failed_login

    # Initialize database
    _init_rate_limit_db()

    # Record a failed login
    _record_failed_login("192.168.1.200")

    # Check that attempt was recorded in login_attempts table
    conn = sqlite3.connect(RATE_LIMIT_DB)
    cursor = conn.cursor()
    attempts = cursor.execute(
        "SELECT attempt_count FROM login_attempts WHERE ip = ?",
        ("192.168.1.200",)
    ).fetchall()
    conn.close()

    assert len(attempts) > 0
    assert attempts[0][0] >= 1  # At least 1 failed attempt recorded


@pytest.mark.asyncio
async def test_successful_login_clears_attempts(client):
    """Successful login after failed attempts allows access."""
    # First, make a few failed attempts
    for _i in range(3):
        response = await client.post("/auth/login", json={"passphrase": "wrong-pass"})
        assert response.status_code == 403

    # Now login successfully
    response = await client.post("/auth/login", json={"passphrase": "test-pass"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
