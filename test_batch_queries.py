#!/usr/bin/env python3
"""Test script to verify batch query methods work correctly."""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agents.registry import AgentRegistry
from memory.store import Memory
from ml.store import MLStore


def test_memory_batch():
    """Test memory.get_agents_batch()"""
    print("Testing memory.get_agents_batch()...")
    memory = Memory()
    memory.init()

    # Register some test agents
    memory.register_agent("test1", "Test Agent 1", "engineer", "haiku")
    memory.register_agent("test2", "Test Agent 2", "manager", "sonnet")
    memory.register_agent("test3", "Test Agent 3", "qa", "haiku")

    # Test batch query
    agents = memory.get_agents_batch(["test1", "test2", "test3"])
    assert len(agents) == 3, f"Expected 3 agents, got {len(agents)}"
    assert "test1" in agents, "test1 not in results"
    assert agents["test1"]["name"] == "Test Agent 1", "Wrong agent data"
    print("✓ memory.get_agents_batch() works!")

    # Test empty list
    agents = memory.get_agents_batch([])
    assert len(agents) == 0, "Empty list should return empty dict"
    print("✓ Empty list handling works!")

    # Test non-existent agents
    agents = memory.get_agents_batch(["test1", "nonexistent"])
    assert "test1" in agents, "test1 should be in results"
    assert "nonexistent" not in agents, "nonexistent should not be in results"
    print("✓ Missing agent handling works!")

def test_registry_batch():
    """Test registry.get_agents_batch()"""
    print("\nTesting registry.get_agents_batch()...")
    registry = AgentRegistry(db_path="/tmp/test_registry.db")  # noqa: S108

    # Load initial config if empty
    if not registry.is_initialized():
        registry.load_from_yaml()

    # Get some agent IDs
    agents = registry.get_active_agents()
    if len(agents) < 3:
        print("⚠ Not enough agents to test batch query")
        return

    agent_ids = [a.id for a in agents[:3]]

    # Test batch query
    batch = registry.get_agents_batch(agent_ids)
    assert len(batch) == 3, f"Expected 3 agents, got {len(batch)}"
    for aid in agent_ids:
        assert aid in batch, f"{aid} not in batch results"
    print("✓ registry.get_agents_batch() works!")

    # Test empty list
    batch = registry.get_agents_batch([])
    assert len(batch) == 0, "Empty list should return empty dict"
    print("✓ Empty list handling works!")

def test_ml_batch():
    """Test ml_store.get_agent_success_rates_batch()"""
    print("\nTesting ml_store.get_agent_success_rates_batch()...")
    ml_store = MLStore(db_path="/tmp/test_ml.db")  # noqa: S108
    ml_store.init()

    # Record some test outcomes
    ml_store.record_outcome(
        directive_id="dir1",
        task_id="task1",
        agent_id="agent1",
        task_description="Test task",
        outcome="complete",
        cost_usd=0.05,
        duration_sec=10.0
    )
    ml_store.record_outcome(
        directive_id="dir1",
        task_id="task2",
        agent_id="agent2",
        task_description="Test task",
        outcome="failed",
        cost_usd=0.03,
        duration_sec=5.0
    )

    # Test batch query
    stats = ml_store.get_agent_success_rates_batch(["agent1", "agent2", "agent3"])
    assert len(stats) == 3, f"Expected 3 entries, got {len(stats)}"
    assert stats["agent1"]["total_tasks"] == 1, "agent1 should have 1 task"
    assert stats["agent1"]["success_rate"] == 1.0, "agent1 should have 100% success"
    assert stats["agent2"]["total_tasks"] == 1, "agent2 should have 1 task"
    assert stats["agent2"]["success_rate"] == 0.0, "agent2 should have 0% success"
    assert stats["agent3"]["total_tasks"] == 0, "agent3 should have 0 tasks"
    print("✓ ml_store.get_agent_success_rates_batch() works!")

    # Test empty list
    stats = ml_store.get_agent_success_rates_batch([])
    assert len(stats) == 0, "Empty list should return empty dict"
    print("✓ Empty list handling works!")

def test_registry_reliability_batch():
    """Test registry.get_agent_reliability_batch()"""
    print("\nTesting registry.get_agent_reliability_batch()...")
    registry = AgentRegistry(db_path="/tmp/test_registry2.db")  # noqa: S108

    # Load initial config
    if not registry.is_initialized():
        registry.load_from_yaml()

    # Record some circuit events
    registry.record_circuit_event("agent1", "trip", "timeout")
    registry.record_circuit_event("agent1", "recovery", "")
    registry.record_circuit_event("agent2", "trip", "error")

    # Test batch query
    stats = registry.get_agent_reliability_batch(["agent1", "agent2", "agent3"])
    assert len(stats) == 3, f"Expected 3 entries, got {len(stats)}"
    assert stats["agent1"]["circuit_trips"] == 1, "agent1 should have 1 trip"
    assert stats["agent1"]["recoveries"] == 1, "agent1 should have 1 recovery"
    assert stats["agent2"]["circuit_trips"] == 1, "agent2 should have 1 trip"
    assert stats["agent2"]["recoveries"] == 0, "agent2 should have 0 recoveries"
    assert stats["agent3"]["circuit_trips"] == 0, "agent3 should have 0 trips"
    print("✓ registry.get_agent_reliability_batch() works!")

if __name__ == "__main__":
    try:
        test_memory_batch()
        test_registry_batch()
        test_ml_batch()
        test_registry_reliability_batch()
        print("\n✅ All batch query tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
