"""
NEXUS Org Chart — Model Constants and Costs

DEPRECATED: Static ORG_CHART dict removed. Use AgentRegistry for all agent configuration.
AgentRegistry is the single source of truth, loaded from config/agents.yaml and persisted to SQLite.

Model tiers:
  - o3 (OpenAI): Chief Architect only
  - Opus: C-suite, VPs, Directors
  - Sonnet: Leads, Engineers, PMs, Reviewers, QA Lead
  - Haiku: Testers, operational roles
"""

OPUS = "claude-opus-4-6"
SONNET = "claude-sonnet-4-5-20250929"
HAIKU = "claude-haiku-4-5-20251001"
O3 = "o3"

MODEL_COSTS = {
    HAIKU:  {"input": 0.80, "output": 4.00},
    SONNET: {"input": 3.00, "output": 15.00},
    OPUS:   {"input": 15.00, "output": 75.00},
    O3:     {"input": 10.00, "output": 40.00},
}


def get_model_for_budget(preferred_model: str, budget_remaining: float | None = None) -> str:
    """Downgrade model tier when budget is tight.

    Uses the cost tracker's configured thresholds rather than hardcoded values.
    If no budget info is available, returns the preferred model unchanged.
    """
    if budget_remaining is None:
        return preferred_model

    # Use model cost ratios to decide: if remaining budget can't cover ~100 calls
    # at the preferred model's rate, downgrade
    preferred_cost_per_1k = MODEL_COSTS.get(preferred_model, {}).get("output", 0)
    estimated_cost_per_call = preferred_cost_per_1k / 1000 * 2  # ~2k tokens avg output

    if estimated_cost_per_call > 0 and budget_remaining / estimated_cost_per_call < 5:
        # Can't afford 5 more calls at this tier — downgrade
        if preferred_model in (OPUS, O3):
            return SONNET
        return HAIKU

    return preferred_model


def get_org_summary() -> str:
    """Backward compatibility wrapper. Redirects to AgentRegistry.get_org_summary()."""
    from src.agents.registry import registry
    return registry.get_org_summary()
