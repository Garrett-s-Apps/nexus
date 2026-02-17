"""
Comprehensive security audit logging (SEC-015).

Logs security-relevant events with structured data:
- Authentication attempts (success/failure)
- Authorization failures
- Rate limit violations
- Session creation/destruction
- API key usage
- Database encryption key access
- Configuration changes
- Sensitive data access

Features:
- Structured logging with timestamp, user, action, result, IP address
- Log rotation to prevent unbounded growth
- Severity levels for filtering
- No PII logged in plaintext (hashes or redaction)
- SQLite storage for audit trail
"""

import hashlib
import json
import logging
import sqlite3
import time
from enum import Enum
from pathlib import Path
from typing import Any

from src.config import NEXUS_DIR

logger = logging.getLogger("nexus.audit_log")

# Severity levels for audit events
class AuditSeverity(Enum):
    """Security event severity levels."""
    INFO = "INFO"           # Informational: normal security events
    WARNING = "WARNING"     # Warning: suspicious but not critical
    CRITICAL = "CRITICAL"  # Critical: security violation or breach attempt


# Event types
class AuditEventType(Enum):
    """Categorized security event types."""
    AUTH_LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    AUTH_LOGIN_FAILURE = "AUTH_LOGIN_FAILURE"
    AUTH_LOGOUT = "AUTH_LOGOUT"
    AUTH_SESSION_CREATED = "AUTH_SESSION_CREATED"
    AUTH_SESSION_DESTROYED = "AUTH_SESSION_DESTROYED"
    AUTH_SESSION_EXPIRED = "AUTH_SESSION_EXPIRED"
    AUTH_SESSION_THEFT_DETECTED = "AUTH_SESSION_THEFT_DETECTED"

    AUTHZ_FAILURE = "AUTHZ_FAILURE"
    AUTHZ_GRANT = "AUTHZ_GRANT"

    RATE_LIMIT_VIOLATED = "RATE_LIMIT_VIOLATED"
    RATE_LIMIT_LOCKOUT = "RATE_LIMIT_LOCKOUT"
    RATE_LIMIT_PERMANENT = "RATE_LIMIT_PERMANENT"

    API_KEY_USED = "API_KEY_USED"
    API_KEY_GENERATED = "API_KEY_GENERATED"
    API_KEY_REVOKED = "API_KEY_REVOKED"

    ENCRYPTION_KEY_ACCESSED = "ENCRYPTION_KEY_ACCESSED"
    ENCRYPTION_KEY_ROTATED = "ENCRYPTION_KEY_ROTATED"
    ENCRYPTION_KEY_GENERATED = "ENCRYPTION_KEY_GENERATED"

    CONFIG_CHANGED = "CONFIG_CHANGED"

    SENSITIVE_DATA_ACCESSED = "SENSITIVE_DATA_ACCESSED"

    JWT_SIGNED = "JWT_SIGNED"
    JWT_VERIFIED = "JWT_VERIFIED"
    JWT_VERIFY_FAILED = "JWT_VERIFY_FAILED"


AUDIT_LOG_DB = Path(NEXUS_DIR) / "audit.db"


def init_audit_db():
    """Initialize the audit log database with required schema."""
    AUDIT_LOG_DB.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(AUDIT_LOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            user_id TEXT,
            user_ip TEXT,
            user_agent TEXT,
            action TEXT NOT NULL,
            result TEXT NOT NULL,
            details TEXT,
            pii_hash TEXT
        )
    """)

    # Index for common queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_events(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON audit_events(event_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_ip ON audit_events(user_ip)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_severity ON audit_events(severity)")

    conn.commit()
    conn.close()


def _redact_pii(value: str, hash_it: bool = True) -> str:
    """Redact PII by hashing (not plaintext) or returning a placeholder."""
    if not value:
        return "[REDACTED]"

    if hash_it:
        return f"hash_{hashlib.sha256(value.encode()).hexdigest()[:16]}"
    return "[REDACTED]"


def _serialize_details(details: dict[str, Any] | None) -> str:
    """Serialize details dict to JSON, safely handling errors."""
    if not details:
        return ""

    try:
        return json.dumps(details, default=str)
    except Exception as e:
        logger.warning("Failed to serialize audit details: %s", e)
        return json.dumps({"serialization_error": str(e)})


def log_auth_attempt(
    success: bool,
    user_ip: str,
    user_agent: str = "",
    username: str | None = None,
    failure_reason: str | None = None,
    details: dict[str, Any] | None = None,
):
    """Log an authentication attempt (login)."""
    init_audit_db()

    event_type = AuditEventType.AUTH_LOGIN_SUCCESS if success else AuditEventType.AUTH_LOGIN_FAILURE
    severity = AuditSeverity.INFO if success else AuditSeverity.WARNING
    result = "success" if success else "failure"

    action_details = details or {}
    if failure_reason:
        action_details["reason"] = failure_reason

    _log_event(
        event_type=event_type,
        severity=severity,
        user_id=_redact_pii(username) if username else None,
        user_ip=user_ip,
        user_agent=user_agent,
        action="LOGIN",
        result=result,
        details=action_details,
    )


def log_session_event(
    event: str,  # "created", "destroyed", "expired", "theft_detected"
    session_id: str | None = None,
    user_ip: str = "",
    user_agent: str = "",
    details: dict[str, Any] | None = None,
):
    """Log session lifecycle events."""
    init_audit_db()

    event_map = {
        "created": (AuditEventType.AUTH_SESSION_CREATED, AuditSeverity.INFO),
        "destroyed": (AuditEventType.AUTH_SESSION_DESTROYED, AuditSeverity.INFO),
        "expired": (AuditEventType.AUTH_SESSION_EXPIRED, AuditSeverity.INFO),
        "theft_detected": (AuditEventType.AUTH_SESSION_THEFT_DETECTED, AuditSeverity.CRITICAL),
    }

    event_type, severity = event_map.get(event, (AuditEventType.AUTH_SESSION_CREATED, AuditSeverity.INFO))

    action_details = details or {}
    if session_id:
        # Hash the session ID to avoid storing sensitive identifiers
        action_details["session_id_hash"] = hashlib.sha256(session_id.encode()).hexdigest()[:16]

    _log_event(
        event_type=event_type,
        severity=severity,
        user_ip=user_ip,
        user_agent=user_agent,
        action=f"SESSION_{event.upper()}",
        result="success",
        details=action_details,
    )


def log_authz_failure(
    user_ip: str,
    resource: str,
    reason: str,
    user_id: str | None = None,
    details: dict[str, Any] | None = None,
):
    """Log an authorization failure."""
    init_audit_db()

    action_details = details or {}
    action_details["resource"] = resource
    action_details["reason"] = reason

    _log_event(
        event_type=AuditEventType.AUTHZ_FAILURE,
        severity=AuditSeverity.WARNING,
        user_id=_redact_pii(user_id) if user_id else None,
        user_ip=user_ip,
        action="AUTHZ_DENIED",
        result="denied",
        details=action_details,
    )


def log_rate_limit_violation(
    user_ip: str,
    attempt_count: int,
    lockout_duration: int | None = None,
    details: dict[str, Any] | None = None,
):
    """Log rate limit violations."""
    init_audit_db()

    # Determine severity based on severity of lockout
    if lockout_duration == float('inf'):
        event_type = AuditEventType.RATE_LIMIT_PERMANENT
        severity = AuditSeverity.CRITICAL
        result = "permanent_lockout"
    elif lockout_duration is not None and lockout_duration > 0:
        event_type = AuditEventType.RATE_LIMIT_LOCKOUT
        severity = AuditSeverity.WARNING
        result = f"locked_{lockout_duration}s"
    else:
        event_type = AuditEventType.RATE_LIMIT_VIOLATED
        severity = AuditSeverity.WARNING
        result = "rate_limit_exceeded"

    action_details = details or {}
    action_details["attempt_count"] = attempt_count
    if lockout_duration and lockout_duration != float('inf'):
        action_details["lockout_duration_seconds"] = lockout_duration

    _log_event(
        event_type=event_type,
        severity=severity,
        user_ip=user_ip,
        action="RATE_LIMIT_CHECK",
        result=result,
        details=action_details,
    )


def log_api_key_event(
    event: str,  # "used", "generated", "revoked"
    key_id: str,
    user_ip: str = "",
    user_id: str | None = None,
    details: dict[str, Any] | None = None,
):
    """Log API key usage and lifecycle events."""
    init_audit_db()

    event_map = {
        "used": (AuditEventType.API_KEY_USED, AuditSeverity.INFO),
        "generated": (AuditEventType.API_KEY_GENERATED, AuditSeverity.INFO),
        "revoked": (AuditEventType.API_KEY_REVOKED, AuditSeverity.INFO),
    }

    event_type, severity = event_map.get(event, (AuditEventType.API_KEY_USED, AuditSeverity.INFO))

    action_details = details or {}
    # Hash the key ID to avoid storing sensitive identifiers
    action_details["key_id_hash"] = hashlib.sha256(key_id.encode()).hexdigest()[:16]

    _log_event(
        event_type=event_type,
        severity=severity,
        user_id=_redact_pii(user_id) if user_id else None,
        user_ip=user_ip,
        action=f"API_KEY_{event.upper()}",
        result="success",
        details=action_details,
    )


def log_encryption_key_event(
    event: str,  # "accessed", "rotated", "generated"
    key_type: str,
    user_id: str | None = None,
    user_ip: str = "",
    details: dict[str, Any] | None = None,
):
    """Log encryption key operations."""
    init_audit_db()

    event_map = {
        "accessed": (AuditEventType.ENCRYPTION_KEY_ACCESSED, AuditSeverity.INFO),
        "rotated": (AuditEventType.ENCRYPTION_KEY_ROTATED, AuditSeverity.INFO),
        "generated": (AuditEventType.ENCRYPTION_KEY_GENERATED, AuditSeverity.INFO),
    }

    event_type, severity = event_map.get(event, (AuditEventType.ENCRYPTION_KEY_ACCESSED, AuditSeverity.INFO))

    action_details = details or {}
    action_details["key_type"] = key_type

    _log_event(
        event_type=event_type,
        severity=severity,
        user_id=_redact_pii(user_id) if user_id else None,
        user_ip=user_ip,
        action=f"ENCRYPTION_KEY_{event.upper()}",
        result="success",
        details=action_details,
    )


def log_sensitive_data_access(
    data_type: str,
    user_id: str | None = None,
    user_ip: str = "",
    user_agent: str = "",
    details: dict[str, Any] | None = None,
):
    """Log access to sensitive data (configs, secrets, etc.)."""
    init_audit_db()

    action_details = details or {}
    action_details["data_type"] = data_type

    _log_event(
        event_type=AuditEventType.SENSITIVE_DATA_ACCESSED,
        severity=AuditSeverity.WARNING,
        user_id=_redact_pii(user_id) if user_id else None,
        user_ip=user_ip,
        user_agent=user_agent,
        action="SENSITIVE_DATA_READ",
        result="accessed",
        details=action_details,
    )


def log_config_change(
    config_key: str,
    old_value: str | None = None,
    new_value: str | None = None,
    user_id: str | None = None,
    user_ip: str = "",
    details: dict[str, Any] | None = None,
):
    """Log configuration changes."""
    init_audit_db()

    action_details = details or {}
    action_details["config_key"] = config_key
    if old_value:
        action_details["old_value_hash"] = hashlib.sha256(old_value.encode()).hexdigest()[:16]
    if new_value:
        action_details["new_value_hash"] = hashlib.sha256(new_value.encode()).hexdigest()[:16]

    _log_event(
        event_type=AuditEventType.CONFIG_CHANGED,
        severity=AuditSeverity.WARNING,
        user_id=_redact_pii(user_id) if user_id else None,
        user_ip=user_ip,
        action="CONFIG_UPDATE",
        result="changed",
        details=action_details,
    )


def log_jwt_event(
    event: str,  # "signed", "verified", "verify_failed"
    user_ip: str = "",
    details: dict[str, Any] | None = None,
):
    """Log JWT operations."""
    init_audit_db()

    event_map = {
        "signed": (AuditEventType.JWT_SIGNED, AuditSeverity.INFO),
        "verified": (AuditEventType.JWT_VERIFIED, AuditSeverity.INFO),
        "verify_failed": (AuditEventType.JWT_VERIFY_FAILED, AuditSeverity.WARNING),
    }

    event_type, severity = event_map.get(event, (AuditEventType.JWT_SIGNED, AuditSeverity.INFO))

    action_details = details or {}

    _log_event(
        event_type=event_type,
        severity=severity,
        user_ip=user_ip,
        action=f"JWT_{event.upper()}",
        result="success" if event != "verify_failed" else "failed",
        details=action_details,
    )


def _log_event(
    event_type: AuditEventType,
    severity: AuditSeverity,
    action: str,
    result: str,
    user_id: str | None = None,
    user_ip: str = "",
    user_agent: str = "",
    details: dict[str, Any] | None = None,
    pii_hash: str | None = None,
):
    """Internal: insert an audit event into the database."""
    try:
        conn = sqlite3.connect(AUDIT_LOG_DB)
        conn.execute(
            """
            INSERT INTO audit_events
            (timestamp, event_type, severity, user_id, user_ip, user_agent, action, result, details, pii_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                event_type.value,
                severity.value,
                user_id,
                user_ip,
                user_agent,
                action,
                result,
                _serialize_details(details),
                pii_hash,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Failed to log audit event: %s", e)


def get_audit_log(
    event_type: str | None = None,
    severity: str | None = None,
    user_ip: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Retrieve audit log entries with optional filtering."""
    try:
        init_audit_db()
        conn = sqlite3.connect(AUDIT_LOG_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM audit_events WHERE 1=1"
        params = []

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if user_ip:
            query += " AND user_ip = ?"
            params.append(user_ip)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([str(limit), str(offset)])

        rows = cursor.execute(query, params).fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.error("Failed to retrieve audit log: %s", e)
        return []


def prune_old_audit_logs(days: int = 90):
    """Delete audit log entries older than the specified number of days."""
    try:
        init_audit_db()
        conn = sqlite3.connect(AUDIT_LOG_DB)

        cutoff_time = time.time() - (days * 24 * 3600)
        conn.execute(
            "DELETE FROM audit_events WHERE timestamp < ?",
            (cutoff_time,),
        )
        deleted = conn.total_changes
        conn.commit()
        conn.close()

        logger.info("Pruned %d old audit log entries (older than %d days)", deleted, days)
    except Exception as e:
        logger.error("Failed to prune audit logs: %s", e)
