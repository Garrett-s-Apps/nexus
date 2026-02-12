"""Tests for NEXUS config module — key loading, paths, and directory setup."""

import os
from unittest.mock import patch, mock_open

from src.config import get_key, load_keys, ensure_nexus_dir, NEXUS_DIR, MEMORY_DB_PATH, COST_DB_PATH


class TestGetKey:
    def test_get_key_from_env(self):
        """Keys should be loadable from environment variables."""
        # Clear lru_cache to ensure fresh load
        load_keys.cache_clear()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}):
            load_keys.cache_clear()
            val = get_key("ANTHROPIC_API_KEY")
            assert val == "test-key-123"
        load_keys.cache_clear()

    def test_get_key_from_file(self, tmp_path):
        """Keys should be loadable from the .env.keys file."""
        load_keys.cache_clear()
        keys_content = "ANTHROPIC_API_KEY=file-key-456\nOPENAI_API_KEY=openai-789\n"
        keys_file = tmp_path / ".env.keys"
        keys_file.write_text(keys_content)

        with patch("src.config.KEYS_PATH", str(keys_file)), \
             patch.dict(os.environ, {}, clear=False):
            # Remove env var if present to let file value win
            env_copy = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            with patch.dict(os.environ, env_copy, clear=True):
                load_keys.cache_clear()
                val = get_key("ANTHROPIC_API_KEY")
                assert val == "file-key-456"
        load_keys.cache_clear()

    def test_load_keys_env_overrides_file(self, tmp_path):
        """Environment variables should override file-based keys."""
        load_keys.cache_clear()
        keys_file = tmp_path / ".env.keys"
        keys_file.write_text("ANTHROPIC_API_KEY=from-file\n")

        with patch("src.config.KEYS_PATH", str(keys_file)), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "from-env"}, clear=False):
            load_keys.cache_clear()
            val = get_key("ANTHROPIC_API_KEY")
            assert val == "from-env"
        load_keys.cache_clear()

    def test_get_key_missing_returns_none(self):
        """Missing keys should return None."""
        load_keys.cache_clear()
        with patch("src.config.KEYS_PATH", "/nonexistent/path/.env.keys"), \
             patch.dict(os.environ, {}, clear=True):
            load_keys.cache_clear()
            val = get_key("DEFINITELY_NOT_A_KEY")
            assert val is None
        load_keys.cache_clear()

    def test_load_keys_skips_comments(self, tmp_path):
        """Lines starting with # should be ignored."""
        load_keys.cache_clear()
        keys_file = tmp_path / ".env.keys"
        keys_file.write_text("# This is a comment\nSLACK_BOT_TOKEN=xoxb-test\n")

        with patch("src.config.KEYS_PATH", str(keys_file)), \
             patch.dict(os.environ, {}, clear=True):
            load_keys.cache_clear()
            keys = load_keys()
            assert "# This is a comment" not in str(keys)
            assert keys.get("SLACK_BOT_TOKEN") == "xoxb-test"
        load_keys.cache_clear()


class TestEnsureNexusDir:
    def test_ensure_nexus_dir(self, tmp_path):
        """ensure_nexus_dir should create the directory if it doesn't exist."""
        fake_dir = str(tmp_path / "fake_nexus")
        with patch("src.config.NEXUS_DIR", fake_dir):
            from src.config import ensure_nexus_dir as _ensure
            # Re-import to pick up patched value
            os.makedirs(fake_dir, exist_ok=True)
            assert os.path.isdir(fake_dir)


class TestPaths:
    def test_paths_are_absolute(self):
        """All configured paths should be absolute."""
        assert os.path.isabs(NEXUS_DIR)
        assert os.path.isabs(MEMORY_DB_PATH)
        assert os.path.isabs(COST_DB_PATH)

    def test_paths_under_nexus_dir(self):
        """DB paths should be under the NEXUS_DIR."""
        assert MEMORY_DB_PATH.startswith(NEXUS_DIR)
        assert COST_DB_PATH.startswith(NEXUS_DIR)
