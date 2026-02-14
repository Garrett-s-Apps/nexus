"""Tests for security audit logging (SEC-015)."""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.security.audit_log import (
    AuditEventType,
    AuditSeverity,
    get_audit_log,
    init_audit_db,
    log_api_key_event,
    log_auth_attempt,
    log_authz_failure,
    log_config_change,
    log_encryption_key_event,
    log_jwt_event,
    log_rate_limit_violation,
    log_sensitive_data_access,
    log_session_event,
    prune_old_audit_logs,
    AUDIT_LOG_DB,
)


@pytest.fixture(autouse=True)
def _cleanup_audit_db():
    """Clean up audit database before and after each test."""
    if AUDIT_LOG_DB.exists():
        AUDIT_LOG_DB.unlink()
    yield
    if AUDIT_LOG_DB.exists():
        AUDIT_LOG_DB.unlink()


class TestAuditDatabaseInit:
    """Test audit database initialization."""

    def test_init_creates_database(self):
        """init_audit_db should create the database and schema."""
        init_audit_db()
        assert AUDIT_LOG_DB.exists()

    def test_init_creates_tables(self):
        """init_audit_db should create audit_events table."""
        init_audit_db()
        import sqlite3
        conn = sqlite3.connect(AUDIT_LOG_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_init_creates_indexes(self):
        """init_audit_db should create query performance indexes."""
        init_audit_db()
        import sqlite3
        conn = sqlite3.connect(AUDIT_LOG_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        assert "idx_timestamp" in indexes
        assert "idx_event_type" in indexes
        conn.close()


class TestAuthenticationLogging:
    """Test authentication event logging."""

    def test_log_successful_login(self):
        """log_auth_attempt should log successful login."""
        log_auth_attempt(
            success=True,
            user_ip="192.168.1.1",
            user_agent="Chrome/120",
        )
        logs = get_audit_log(event_type=AuditEventType.AUTH_LOGIN_SUCCESS.value)
        assert len(logs) == 1
        assert logs[0]["result"] == "success"
        assert logs[0]["user_ip"] == "192.168.1.1"

    def test_log_failed_login(self):
        """log_auth_attempt should log failed login with reason."""
        log_auth_attempt(
            success=False,
            user_ip="192.168.1.2",
            user_agent="Firefox/119",
            failure_reason="invalid_passphrase",
        )
        logs = get_audit_log(event_type=AuditEventType.AUTH_LOGIN_FAILURE.value)
        assert len(logs) == 1
        assert logs[0]["result"] == "failure"
        assert logs[0]["severity"] == AuditSeverity.WARNING.value

    def test_log_login_with_username_hashed(self):
        """log_auth_attempt should hash usernames to avoid storing PII."""
        log_auth_attempt(
            success=True,
            user_ip="192.168.1.1",
            username="admin@example.com",
        )
        logs = get_audit_log()
        assert len(logs) == 1
        # Verify username is hashed, not plaintext
        assert "admin@example.com" not in logs[0]["user_id"]
        assert logs[0]["user_id"].startswith("hash_")


class TestSessionLogging:
    """Test session lifecycle logging."""

    def test_log_session_created(self):
        """log_session_event should log session creation."""
        log_session_event(
            event="created",
            session_id="token123.sig456",
            user_ip="192.168.1.1",
            user_agent="Chrome/120",
        )
        logs = get_audit_log(event_type=AuditEventType.AUTH_SESSION_CREATED.value)
        assert len(logs) == 1
        assert logs[0]["action"] == "SESSION_CREATED"

    def test_log_session_destroyed(self):
        """log_session_event should log session destruction."""
        log_session_event(
            event="destroyed",
            session_id="token123.sig456",
            details={"reason": "logout"},
        )
        logs = get_audit_log(event_type=AuditEventType.AUTH_SESSION_DESTROYED.value)
        assert len(logs) == 1
        assert logs[0]["result"] == "success"

    def test_log_session_theft_detection(self):
        """log_session_event should log session theft detection as critical."""
        log_session_event(
            event="theft_detected",
            session_id="token123.sig456",
            user_ip="192.168.1.99",
            details={"reason": "fingerprint_mismatch"},
        )
        logs = get_audit_log(event_type=AuditEventType.AUTH_SESSION_THEFT_DETECTED.value)
        assert len(logs) == 1
        assert logs[0]["severity"] == AuditSeverity.CRITICAL.value

    def test_session_id_hashed_not_stored(self):
        """log_session_event should hash session IDs to avoid leaking them."""
        log_session_event(
            event="created",
            session_id="super_secret_token_12345",
        )
        logs = get_audit_log()
        details = json.loads(logs[0]["details"])
        # Verify session ID is hashed
        assert "super_secret_token_12345" not in logs[0]["details"]
        assert "session_id_hash" in details


class TestAuthorizationLogging:
    """Test authorization failure logging."""

    def test_log_authz_failure(self):
        """log_authz_failure should log authorization denials."""
        log_authz_failure(
            user_ip="192.168.1.1",
            resource="/admin/config",
            reason="insufficient_permissions",
        )
        logs = get_audit_log(event_type=AuditEventType.AUTHZ_FAILURE.value)
        assert len(logs) == 1
        assert logs[0]["result"] == "denied"
        details = json.loads(logs[0]["details"])
        assert details["resource"] == "/admin/config"


class TestRateLimitLogging:
    """Test rate limit violation logging."""

    def test_log_rate_limit_violation(self):
        """log_rate_limit_violation should log violations."""
        log_rate_limit_violation(
            user_ip="192.168.1.1",
            attempt_count=3,
        )
        logs = get_audit_log(event_type=AuditEventType.RATE_LIMIT_VIOLATED.value)
        assert len(logs) == 1
        details = json.loads(logs[0]["details"])
        assert details["attempt_count"] == 3

    def test_log_progressive_lockout(self):
        """log_rate_limit_violation should log progressive lockouts."""
        log_rate_limit_violation(
            user_ip="192.168.1.1",
            attempt_count=10,
            lockout_duration=600,
        )
        logs = get_audit_log(event_type=AuditEventType.RATE_LIMIT_LOCKOUT.value)
        assert len(logs) == 1
        assert logs[0]["severity"] == AuditSeverity.WARNING.value

    def test_log_permanent_lockout(self):
        """log_rate_limit_violation should log permanent lockouts as critical."""
        log_rate_limit_violation(
            user_ip="192.168.1.1",
            attempt_count=20,
            lockout_duration=float('inf'),  # type: ignore  # Permanent lockout
        )
        logs = get_audit_log(event_type=AuditEventType.RATE_LIMIT_PERMANENT.value)
        assert len(logs) == 1
        assert logs[0]["severity"] == AuditSeverity.CRITICAL.value


class TestAPIKeyLogging:
    """Test API key operation logging."""

    def test_log_api_key_used(self):
        """log_api_key_event should log API key usage."""
        log_api_key_event(
            event="used",
            key_id="sk_test_123456",
            user_ip="192.168.1.1",
        )
        logs = get_audit_log(event_type=AuditEventType.API_KEY_USED.value)
        assert len(logs) == 1
        details = json.loads(logs[0]["details"])
        assert "key_id_hash" in details

    def test_log_api_key_generated(self):
        """log_api_key_event should log API key generation."""
        log_api_key_event(
            event="generated",
            key_id="sk_new_789",
            user_id="user_admin",
        )
        logs = get_audit_log(event_type=AuditEventType.API_KEY_GENERATED.value)
        assert len(logs) == 1

    def test_log_api_key_revoked(self):
        """log_api_key_event should log API key revocation."""
        log_api_key_event(
            event="revoked",
            key_id="sk_revoke_456",
            user_id="user_admin",
        )
        logs = get_audit_log(event_type=AuditEventType.API_KEY_REVOKED.value)
        assert len(logs) == 1

    def test_api_key_id_hashed(self):
        """log_api_key_event should hash key IDs to avoid exposure."""
        log_api_key_event(
            event="used",
            key_id="super_secret_key_12345",
        )
        logs = get_audit_log()
        assert "super_secret_key_12345" not in logs[0]["details"]


class TestEncryptionKeyLogging:
    """Test encryption key operation logging."""

    def test_log_encryption_key_accessed(self):
        """log_encryption_key_event should log key access."""
        log_encryption_key_event(
            event="accessed",
            key_type="database_master_key",
        )
        logs = get_audit_log(event_type=AuditEventType.ENCRYPTION_KEY_ACCESSED.value)
        assert len(logs) == 1

    def test_log_encryption_key_rotated(self):
        """log_encryption_key_event should log key rotation."""
        log_encryption_key_event(
            event="rotated",
            key_type="jwt_signing_key",
        )
        logs = get_audit_log(event_type=AuditEventType.ENCRYPTION_KEY_ROTATED.value)
        assert len(logs) == 1

    def test_log_encryption_key_generated(self):
        """log_encryption_key_event should log key generation."""
        log_encryption_key_event(
            event="generated",
            key_type="session_key",
        )
        logs = get_audit_log(event_type=AuditEventType.ENCRYPTION_KEY_GENERATED.value)
        assert len(logs) == 1


class TestSensitiveDataLogging:
    """Test sensitive data access logging."""

    def test_log_sensitive_data_access(self):
        """log_sensitive_data_access should log access to sensitive data."""
        log_sensitive_data_access(
            data_type="api_config",
            user_ip="192.168.1.1",
        )
        logs = get_audit_log(event_type=AuditEventType.SENSITIVE_DATA_ACCESSED.value)
        assert len(logs) == 1
        assert logs[0]["severity"] == AuditSeverity.WARNING.value


class TestConfigChangeLogging:
    """Test configuration change logging."""

    def test_log_config_change(self):
        """log_config_change should log configuration changes."""
        log_config_change(
            config_key="SESSION_TTL",
            old_value="2592000",
            new_value="3600",
            user_ip="192.168.1.1",
        )
        logs = get_audit_log(event_type=AuditEventType.CONFIG_CHANGED.value)
        assert len(logs) == 1
        details = json.loads(logs[0]["details"])
        assert details["config_key"] == "SESSION_TTL"
        # Verify values are hashed, not stored plaintext
        assert "old_value_hash" in details
        assert "new_value_hash" in details
        assert "2592000" not in logs[0]["details"]


class TestJWTLogging:
    """Test JWT operation logging."""

    def test_log_jwt_signed(self):
        """log_jwt_event should log JWT signing."""
        log_jwt_event(
            event="signed",
            details={"algorithm": "RS256"},
        )
        logs = get_audit_log(event_type=AuditEventType.JWT_SIGNED.value)
        assert len(logs) == 1

    def test_log_jwt_verified(self):
        """log_jwt_event should log JWT verification."""
        log_jwt_event(
            event="verified",
            details={"algorithm": "RS256", "valid": True},
        )
        logs = get_audit_log(event_type=AuditEventType.JWT_VERIFIED.value)
        assert len(logs) == 1

    def test_log_jwt_verify_failed(self):
        """log_jwt_event should log JWT verification failures."""
        log_jwt_event(
            event="verify_failed",
            details={"reason": "invalid_signature"},
        )
        logs = get_audit_log(event_type=AuditEventType.JWT_VERIFY_FAILED.value)
        assert len(logs) == 1
        assert logs[0]["result"] == "failed"


class TestAuditLogFiltering:
    """Test audit log retrieval with filtering."""

    def test_get_audit_log_by_event_type(self):
        """get_audit_log should filter by event type."""
        log_auth_attempt(success=True, user_ip="1.1.1.1")
        log_auth_attempt(success=False, user_ip="2.2.2.2")
        log_rate_limit_violation(user_ip="3.3.3.3", attempt_count=5)

        success_logs = get_audit_log(event_type=AuditEventType.AUTH_LOGIN_SUCCESS.value)
        assert len(success_logs) == 1
        assert success_logs[0]["user_ip"] == "1.1.1.1"

    def test_get_audit_log_by_severity(self):
        """get_audit_log should filter by severity."""
        log_auth_attempt(success=False, user_ip="1.1.1.1")
        log_session_event(event="theft_detected", user_ip="2.2.2.2")

        critical_logs = get_audit_log(severity=AuditSeverity.CRITICAL.value)
        assert len(critical_logs) == 1
        assert critical_logs[0]["event_type"] == AuditEventType.AUTH_SESSION_THEFT_DETECTED.value

    def test_get_audit_log_by_user_ip(self):
        """get_audit_log should filter by user IP."""
        log_auth_attempt(success=True, user_ip="192.168.1.1")
        log_auth_attempt(success=True, user_ip="192.168.1.2")

        ip_logs = get_audit_log(user_ip="192.168.1.1")
        assert len(ip_logs) == 1
        assert ip_logs[0]["user_ip"] == "192.168.1.1"

    def test_get_audit_log_limit(self):
        """get_audit_log should respect limit parameter."""
        for i in range(10):
            log_auth_attempt(success=True, user_ip=f"192.168.1.{i}")

        logs = get_audit_log(limit=5)
        assert len(logs) == 5

    def test_get_audit_log_offset(self):
        """get_audit_log should respect offset parameter."""
        for i in range(10):
            log_auth_attempt(success=True, user_ip=f"192.168.1.{i}")

        logs_page1 = get_audit_log(limit=5, offset=0)
        logs_page2 = get_audit_log(limit=5, offset=5)

        assert len(logs_page1) == 5
        assert len(logs_page2) == 5
        assert logs_page1[0]["id"] != logs_page2[0]["id"]


class TestAuditLogPruning:
    """Test audit log retention and pruning."""

    def test_prune_old_audit_logs(self):
        """prune_old_audit_logs should delete old entries."""
        import sqlite3

        # Create an old entry (91 days ago)
        init_audit_db()
        conn = sqlite3.connect(AUDIT_LOG_DB)
        old_timestamp = time.time() - (91 * 24 * 3600)
        conn.execute(
            """INSERT INTO audit_events
               (timestamp, event_type, severity, action, result)
               VALUES (?, ?, ?, ?, ?)""",
            (old_timestamp, "TEST_EVENT", "INFO", "TEST", "success")
        )
        # Create a recent entry
        conn.execute(
            """INSERT INTO audit_events
               (timestamp, event_type, severity, action, result)
               VALUES (?, ?, ?, ?, ?)""",
            (time.time(), "TEST_EVENT", "INFO", "TEST", "success")
        )
        conn.commit()
        conn.close()

        # Prune
        prune_old_audit_logs(days=90)

        # Verify old entry is deleted
        logs = get_audit_log()
        assert len(logs) == 1
        # Recent entry should remain (timestamp should be recent)
        assert logs[0]["timestamp"] > (time.time() - 1000)


class TestAuditLogDetails:
    """Test that audit log details are properly serialized."""

    def test_details_serialized_to_json(self):
        """Audit details should be serialized to JSON."""
        log_auth_attempt(
            success=True,
            user_ip="192.168.1.1",
            details={"custom_field": "custom_value", "nested": {"key": "value"}},
        )
        logs = get_audit_log()
        details = json.loads(logs[0]["details"])
        assert details["custom_field"] == "custom_value"
        assert details["nested"]["key"] == "value"

    def test_serialization_error_handling(self):
        """Audit logging should handle serialization errors gracefully."""
        # Pass a non-serializable object
        class NonSerializable:
            pass

        log_auth_attempt(
            success=True,
            user_ip="192.168.1.1",
            details={"obj": NonSerializable()},  # type: ignore
        )
        logs = get_audit_log()
        # Should not crash; details should have error info
        assert "serialization_error" in logs[0]["details"] or logs[0]["details"] == ""
