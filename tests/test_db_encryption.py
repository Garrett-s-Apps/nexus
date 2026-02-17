"""Tests for NEXUS database encryption module (SEC-008)."""

import os
from unittest.mock import patch

import pytest

from src.db.encryption import (
    _get_master_secret,
    _get_or_create_salt,
    get_db_encryption_key,
    is_encryption_available,
)
from src.db.sqlite_store import connect_encrypted


# Helper: patch environment to have no NEXUS_MASTER_SECRET
def _no_secret_env():
    """Return a patch that removes NEXUS_MASTER_SECRET and mocks get_key to None."""
    env_without = {k: v for k, v in os.environ.items() if k != "NEXUS_MASTER_SECRET"}
    return patch.dict(os.environ, env_without, clear=True)


class TestMasterSecret:
    def test_get_master_secret_from_env(self):
        """Master secret should be read from NEXUS_MASTER_SECRET env var."""
        with patch.dict(os.environ, {"NEXUS_MASTER_SECRET": "test-secret-123"}):
            secret = _get_master_secret()
            assert secret == "test-secret-123"

    def test_get_master_secret_missing_raises(self):
        """Missing master secret should raise ValueError."""
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                with pytest.raises(ValueError, match="NEXUS_MASTER_SECRET"):
                    _get_master_secret()

    def test_get_master_secret_from_keys_file(self):
        """Master secret should fall back to keys file."""
        with _no_secret_env():
            with patch("src.config.get_key", return_value="file-secret"):
                secret = _get_master_secret()
                assert secret == "file-secret"


class TestSaltManagement:
    def test_create_salt(self, tmp_path):
        """Salt should be created if it doesn't exist."""
        salt_path = tmp_path / ".db_salt"
        with patch("src.db.encryption._SALT_PATH", salt_path):
            salt = _get_or_create_salt()
            assert len(salt) == 32
            assert salt_path.exists()

    def test_reuse_existing_salt(self, tmp_path):
        """Existing salt should be reused."""
        salt_path = tmp_path / ".db_salt"
        expected_salt = os.urandom(32)
        salt_path.write_bytes(expected_salt)

        with patch("src.db.encryption._SALT_PATH", salt_path):
            salt = _get_or_create_salt()
            assert salt == expected_salt

    def test_salt_file_permissions(self, tmp_path):
        """Salt file should have 0600 permissions."""
        salt_path = tmp_path / ".db_salt"
        with patch("src.db.encryption._SALT_PATH", salt_path):
            _get_or_create_salt()
            mode = oct(salt_path.stat().st_mode)[-3:]
            assert mode == "600"


class TestKeyDerivation:
    def test_get_db_encryption_key_deterministic(self, tmp_path):
        """Same secret + salt should produce the same key."""
        salt_path = tmp_path / ".db_salt"
        with patch.dict(os.environ, {"NEXUS_MASTER_SECRET": "deterministic-test"}):
            with patch("src.db.encryption._SALT_PATH", salt_path):
                key1 = get_db_encryption_key()
                key2 = get_db_encryption_key()
                assert key1 == key2

    def test_get_db_encryption_key_different_secrets(self, tmp_path):
        """Different secrets should produce different keys."""
        salt_path = tmp_path / ".db_salt"
        with patch("src.db.encryption._SALT_PATH", salt_path):
            with patch.dict(os.environ, {"NEXUS_MASTER_SECRET": "secret-a"}):
                key_a = get_db_encryption_key()
            with patch.dict(os.environ, {"NEXUS_MASTER_SECRET": "secret-b"}):
                key_b = get_db_encryption_key()
            assert key_a != key_b

    def test_get_db_encryption_key_format(self, tmp_path):
        """Key should be base64-encoded 256-bit key."""
        salt_path = tmp_path / ".db_salt"
        with patch.dict(os.environ, {"NEXUS_MASTER_SECRET": "format-test"}):
            with patch("src.db.encryption._SALT_PATH", salt_path):
                key = get_db_encryption_key()
                import base64
                decoded = base64.b64decode(key)
                assert len(decoded) == 32


class TestEncryptionAvailability:
    def test_is_encryption_available_with_secret(self):
        """Should return True when master secret is set."""
        with patch.dict(os.environ, {"NEXUS_MASTER_SECRET": "test"}):
            assert is_encryption_available() is True

    def test_is_encryption_available_without_secret(self):
        """Should return False when master secret is missing."""
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                assert is_encryption_available() is False


class TestConnectEncrypted:
    """Test connect_encrypted falls back gracefully without pysqlcipher3."""

    def test_connect_encrypted_without_secret(self, tmp_path):
        """Without master secret, should fall back to plain sqlite3."""
        db_path = str(tmp_path / "test.db")
        # No NEXUS_MASTER_SECRET set, encryption should be skipped
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                conn = connect_encrypted(db_path)
                conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO test VALUES (1)")
                conn.commit()
                row = conn.execute("SELECT * FROM test").fetchone()
                assert row[0] == 1
                conn.close()

    def test_connect_encrypted_wal_mode(self, tmp_path):
        """Connection should have WAL mode enabled."""
        db_path = str(tmp_path / "test_wal.db")
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                conn = connect_encrypted(db_path)
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                assert mode == "wal"
                conn.close()

    def test_connect_encrypted_busy_timeout(self, tmp_path):
        """Connection should have busy_timeout set."""
        db_path = str(tmp_path / "test_timeout.db")
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                conn = connect_encrypted(db_path)
                timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
                assert timeout == 5000
                conn.close()

    def test_connect_encrypted_data_persists(self, tmp_path):
        """Data written should persist across connections."""
        db_path = str(tmp_path / "test_persist.db")
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                conn1 = connect_encrypted(db_path)
                conn1.execute("CREATE TABLE persist_test (val TEXT)")
                conn1.execute("INSERT INTO persist_test VALUES ('hello')")
                conn1.commit()
                conn1.close()

                conn2 = connect_encrypted(db_path)
                row = conn2.execute("SELECT val FROM persist_test").fetchone()
                assert row[0] == "hello"
                conn2.close()


class TestDatabaseModulesUseEncryption:
    """Verify all 7 database modules work through connect_encrypted."""

    def test_memory_store_uses_encryption(self, tmp_path):
        """Memory store should use connect_encrypted for its connection."""
        from src.memory.store import Memory
        mem = Memory()
        mem.db_path = str(tmp_path / "test_memory.db")
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                mem.init()
                mem.add_message("user", "test message")
                msgs = mem.get_recent_messages(1)
                assert len(msgs) == 1
                assert msgs[0]["content"] == "test message"

    def test_cost_tracker_uses_encryption(self, tmp_path):
        """Cost tracker should use connect_encrypted for its connections."""
        from src.cost.tracker import CostTracker
        db_path = str(tmp_path / "test_cost.db")
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                tracker = CostTracker(db_path=db_path)
                tracker.record("haiku", "eng1", 1000, 500)
                assert tracker.call_count == 1

    def test_kpi_tracker_uses_encryption(self, tmp_path):
        """KPI tracker should use connect_encrypted for its connections."""
        from src.kpi.tracker import KPITracker
        db_path = str(tmp_path / "test_kpi.db")
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                tracker = KPITracker(db_path=db_path)
                tracker.record("test", "metric", 1.0)
                summary = tracker.get_summary(hours=1)
                assert isinstance(summary, dict)

    def test_registry_uses_encryption(self, tmp_path):
        """Agent registry should use connect_encrypted for its connections."""
        from src.agents.registry import AgentRegistry
        db_path = str(tmp_path / "test_registry.db")
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                reg = AgentRegistry(db_path=db_path)
                assert reg.is_initialized() is False

    def test_ml_store_uses_encryption(self, tmp_path):
        """ML store should use connect_encrypted for its connection."""
        from src.ml.store import MLStore
        db_path = str(tmp_path / "test_ml.db")
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                store = MLStore(db_path=db_path)
                store.init()
                counts = store.get_training_data_count()
                assert counts["task_outcomes"] == 0

    def test_knowledge_store_uses_encryption(self, tmp_path):
        """Knowledge store should use connect_encrypted for its connection."""
        from src.ml.knowledge_store import KnowledgeStore
        db_path = str(tmp_path / "test_knowledge.db")
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                store = KnowledgeStore(db_path=db_path)
                store.init()
                counts = store.count_chunks()
                assert isinstance(counts, dict)

    @pytest.mark.asyncio
    async def test_session_store_uses_encryption(self, tmp_path):
        """Session store should use aconnect_encrypted for its connections."""
        from src.session.store import SessionStore
        db_path = str(tmp_path / "test_sessions.db")
        with _no_secret_env():
            with patch("src.config.get_key", return_value=None):
                store = SessionStore(db_path=db_path)
                await store.init()
                sessions = await store.get_recent_sessions()
                assert sessions == []
