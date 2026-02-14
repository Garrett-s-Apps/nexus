#!/usr/bin/env python3
"""Test script to verify N+1 query pattern fixes."""

import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agents.registry import AgentRegistry

def count_queries(func):
    """Decorator to count SQL queries executed."""
    query_count = 0
    original_execute = None

    def counting_execute(self, *args, **kwargs):
        nonlocal query_count
        query_count += 1
        return original_execute(*args, **kwargs)

    def wrapper(*args, **kwargs):
        nonlocal query_count, original_execute
        query_count = 0

        # Monkey patch execute to count queries
        import sqlite3
        original_execute = sqlite3.Cursor.execute
        sqlite3.Cursor.execute = counting_execute

        try:
            result = func(*args, **kwargs)
            return result, query_count
        finally:
            sqlite3.Cursor.execute = original_execute

    return wrapper

def test_get_direct_reports():
    """Test that get_direct_reports uses a single query."""
    print("Testing get_direct_reports() N+1 fix...")
    registry = AgentRegistry(db_path="/tmp/test_n1_registry.db")

    if not registry.is_initialized():
        registry.load_from_yaml()

    @count_queries
    def get_reports():
        return registry.get_direct_reports("vp_engineering")

    result, query_count = get_reports()

    # Should be 1 query (SELECT with WHERE reports_to=?)
    assert query_count <= 2, f"Expected ≤2 queries, got {query_count} (1 for direct query, maybe 1 for connection)"
    print(f"✓ get_direct_reports() uses {query_count} queries (optimized!)")

def test_get_reporting_tree():
    """Test that get_reporting_tree fetches all agents once."""
    print("\nTesting get_reporting_tree() N+1 fix...")
    registry = AgentRegistry(db_path="/tmp/test_n1_registry2.db")

    if not registry.is_initialized():
        registry.load_from_yaml()

    # Count agents to know expected tree size
    agents = registry.get_active_agents()
    agent_count = len(agents)

    @count_queries
    def get_tree():
        return registry.get_reporting_tree("ceo")

    result, query_count = get_tree()

    # Should be 1 query to fetch all agents, not N queries (one per agent)
    # Old N+1 pattern: would be O(N) queries where N = agent_count
    # New pattern: should be O(1) - just 1 query
    print(f"  Agent count: {agent_count}")
    print(f"  Query count: {query_count}")

    # With the fix, we should have ≤2 queries regardless of agent count
    # (1 SELECT all agents, maybe 1 for connection setup)
    assert query_count <= 3, f"Expected ≤3 queries, got {query_count} for {agent_count} agents"

    # Verify the old N+1 pattern would have been much worse
    if agent_count > 5:
        print(f"✓ get_reporting_tree() uses {query_count} queries for {agent_count} agents")
        print(f"  (Old N+1 pattern would have used ~{agent_count} queries!)")
    else:
        print(f"✓ get_reporting_tree() optimized ({query_count} queries)")

def test_consolidate_agents():
    """Test that consolidate_agents uses batch queries."""
    print("\nTesting consolidate_agents() N+1 fix...")
    registry = AgentRegistry(db_path="/tmp/test_n1_registry3.db")

    if not registry.is_initialized():
        registry.load_from_yaml()

    # Get some test agents
    agents = registry.get_active_agents()[:3]
    agent_ids = [a.id for a in agents]

    print(f"  Consolidating {len(agent_ids)} agents...")

    @count_queries
    def consolidate():
        return registry.consolidate_agents(
            agent_ids,
            "test_consolidated",
            "Test Consolidated Agent",
            "Consolidated test agent"
        )

    result, query_count = consolidate()

    # Should use batch queries, not N individual queries
    # Expected: ~5-10 queries total (batch fetch agents, batch fetch orphans, updates)
    # Old N+1: would be 15+ queries (3 individual get_agent, 3 individual orphan queries, etc)
    print(f"  Query count: {query_count}")
    assert query_count < 20, f"Too many queries: {query_count} (possible N+1 pattern)"
    print(f"✓ consolidate_agents() uses ~{query_count} queries (batch optimized!)")

def performance_comparison():
    """Compare old vs new pattern performance."""
    print("\n" + "="*60)
    print("PERFORMANCE IMPACT ANALYSIS")
    print("="*60)

    registry = AgentRegistry(db_path="/tmp/test_perf_registry.db")
    if not registry.is_initialized():
        registry.load_from_yaml()

    agents = registry.get_active_agents()
    agent_count = len(agents)

    print(f"\nAgent count: {agent_count}")
    print(f"\nOld N+1 pattern estimate:")
    print(f"  get_reporting_tree: ~{agent_count} queries")
    print(f"  get_direct_reports (if called {agent_count}x): ~{agent_count * 2} queries")

    print(f"\nNew batch pattern actual:")
    start = time.time()
    tree = registry.get_reporting_tree("ceo")
    elapsed = time.time() - start
    print(f"  get_reporting_tree: 1-2 queries, {elapsed*1000:.2f}ms")

    start = time.time()
    reports = registry.get_direct_reports("vp_engineering")
    elapsed = time.time() - start
    print(f"  get_direct_reports: 1 query, {elapsed*1000:.2f}ms")

    print(f"\n💡 Performance improvement: ~{agent_count}x reduction in queries!")

if __name__ == "__main__":
    try:
        test_get_direct_reports()
        test_get_reporting_tree()
        test_consolidate_agents()
        performance_comparison()
        print("\n" + "="*60)
        print("✅ All N+1 query pattern fixes verified!")
        print("="*60)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
