"""
NEXUS shared configuration.

Centralizes key loading, paths, and constants used across the codebase.
"""

import os
from functools import lru_cache

NEXUS_DIR = os.path.expanduser("~/.nexus")
KEYS_PATH = os.path.join(NEXUS_DIR, ".env.keys")
MEMORY_DB_PATH = os.path.join(NEXUS_DIR, "memory.db")
COST_DB_PATH = os.path.join(NEXUS_DIR, "cost.db")
KPI_DB_PATH = os.path.join(NEXUS_DIR, "kpi.db")
SESSIONS_DB_PATH = os.path.join(NEXUS_DIR, "sessions.db")

SLACK_CHANNEL_NAME = "garrett-nexus"


@lru_cache(maxsize=1)
def load_keys() -> dict[str, str]:
    """Load all keys from environment variables and ~/.nexus/.env.keys file."""
    keys: dict[str, str] = {}
    try:
        with open(KEYS_PATH) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    keys[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    # Environment variables override file values
    for key in ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_CHANNEL",
                "SLACK_OWNER_USER_ID",
                "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"]:
        val = os.environ.get(key)
        if val:
            keys[key] = val
    return keys


def get_key(key_name: str) -> str | None:
    """Get a single key by name."""
    return load_keys().get(key_name)


def ensure_nexus_dir():
    """Ensure ~/.nexus directory exists."""
    os.makedirs(NEXUS_DIR, exist_ok=True)
