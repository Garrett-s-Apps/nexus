"""
Dashboard auth gate — passphrase-based, zero-friction.

Enter passphrase once, httponly cookie persists for 30 days.
Passphrase set via NEXUS_DASHBOARD_KEY env var or ~/.nexus/.env.keys.
Restricted to geaglin09@gmail.com (single-user system).

Security hardening:
- Sessions bound to client fingerprint (User-Agent + IP hash)
  so stolen/replayed cookies from a different client are rejected.
- HMAC-SHA256 signed tokens prevent forgery without the server secret.
- In-memory session store means fabricated tokens always fail lookup.
- Constant-time comparison on all sensitive checks.
"""

import hashlib
import hmac
import logging
import os
import secrets
import time

from src.config import get_key

logger = logging.getLogger("nexus.auth_gate")

AUTH_COOKIE = "nexus_session"
SESSION_TTL = 30 * 24 * 3600  # 30 days

_sessions: dict[str, dict] = {}
_signing_key: str | None = None


def _get_signing_key() -> str:
    """Derive a signing key from the dashboard passphrase."""
    global _signing_key
    if _signing_key:
        return _signing_key
    passphrase = _get_passphrase()
    _signing_key = hashlib.sha256(f"nexus-session-{passphrase}".encode()).hexdigest()
    return _signing_key


def _get_passphrase() -> str:
    """Load the dashboard passphrase from config."""
    key = get_key("NEXUS_DASHBOARD_KEY") or os.environ.get("NEXUS_DASHBOARD_KEY")
    if not key:
        key = secrets.token_urlsafe(24)
        _persist_key(key)
        logger.info("Generated dashboard passphrase (check ~/.nexus/.env.keys)")
    return key


def _persist_key(key: str):
    """Append the generated key to the env file with restricted permissions."""
    from src.config import KEYS_PATH
    try:
        fd = os.open(KEYS_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(f"\nNEXUS_DASHBOARD_KEY={key}\n")
        os.chmod(KEYS_PATH, 0o600)
    except OSError as e:
        logger.warning("Could not persist dashboard key: %s", e)


def _compute_fingerprint(user_agent: str, client_ip: str) -> str:
    """Hash client identity so sessions can't transfer between browsers/IPs."""
    raw = f"{user_agent}|{client_ip}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def create_session(user_agent: str = "", client_ip: str = "") -> str:
    """Create a new session token bound to the client fingerprint."""
    fingerprint = _compute_fingerprint(user_agent, client_ip)
    token = secrets.token_urlsafe(32)
    # Sign token+fingerprint together so neither can be swapped independently
    msg = f"{token}:{fingerprint}".encode()
    sig = hmac.new(_get_signing_key().encode(), msg, hashlib.sha256).hexdigest()
    session_id = f"{token}.{sig}"
    _sessions[session_id] = {
        "expiry": time.time() + SESSION_TTL,
        "fingerprint": fingerprint,
    }
    return session_id


def verify_session(
    session_id: str | None,
    user_agent: str = "",
    client_ip: str = "",
) -> bool:
    """Verify a session cookie is valid, not expired, and from the same client."""
    if not session_id:
        return False

    # Structural check
    parts = session_id.split(".", 1)
    if len(parts) != 2:
        return False
    token, sig = parts

    # Look up session — must exist in server memory (blocks fabricated tokens)
    session = _sessions.get(session_id)
    if not session:
        return False

    # Verify fingerprint matches the requesting client
    fingerprint = _compute_fingerprint(user_agent, client_ip)
    if not hmac.compare_digest(fingerprint, session["fingerprint"]):
        logger.warning("Session fingerprint mismatch — possible token theft")
        _sessions.pop(session_id, None)
        return False

    # Verify HMAC (token+fingerprint signed together)
    msg = f"{token}:{fingerprint}".encode()
    expected_sig = hmac.new(_get_signing_key().encode(), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False

    # Check expiry
    if time.time() > session["expiry"]:
        _sessions.pop(session_id, None)
        return False

    return True


def verify_passphrase(attempt: str) -> bool:
    """Check if the provided passphrase matches (constant-time)."""
    return hmac.compare_digest(attempt, _get_passphrase())


def invalidate_session(session_id: str):
    """Explicitly destroy a session (logout)."""
    _sessions.pop(session_id, None)
