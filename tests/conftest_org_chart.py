"""Pytest configuration for org_chart tests."""
import os
import pytest


@pytest.fixture(scope="session", autouse=True)
def clean_agent_registry():
    """Delete agent database before tests to ensure fresh load from YAML."""
    db_path = os.path.expanduser("~/.nexus/registry.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    yield
