"""
Directive Similarity Search — "We've done something like this before."

When a new directive arrives, searches past directives by semantic similarity
and returns:
- What we did before (task breakdown, agents used)
- How much it cost
- What went wrong (defect patterns)

This feeds the kickoff phase so the engine can make smarter decisions
about decomposition, agent assignment, and budget estimation.
"""

import logging

from src.ml.feedback import find_similar_directives_async as find_similar_directives
from src.ml.predictor import predict_cost
from src.ml.store import ml_store

logger = logging.getLogger("nexus.ml.similarity")


async def analyze_new_directive(directive_text: str) -> dict:
    """Analyze a new directive against historical data.

    Returns a briefing with similar past work, cost estimate, and risk factors.
    """
    similar = await find_similar_directives(directive_text, top_k=3)
    cost_estimate = predict_cost(directive_text)

    # Compute average metrics from similar directives
    avg_cost = 0.0
    avg_tasks = 0
    avg_duration = 0.0
    success_count = 0

    if similar:
        costs = [s["total_cost"] for s in similar if s["total_cost"] > 0]
        tasks = [s["total_tasks"] for s in similar if s["total_tasks"] > 0]
        durations = [s["total_duration_sec"] for s in similar if s["total_duration_sec"] > 0]

        avg_cost = sum(costs) / len(costs) if costs else 0
        avg_tasks = int(sum(tasks) / len(tasks)) if tasks else 0
        avg_duration = sum(durations) / len(durations) if durations else 0
        success_count = sum(1 for s in similar if s["outcome"] == "complete")

    # Risk assessment based on historical data
    risk = "low"
    risk_factors = []

    if similar:
        failure_rate = 1 - (success_count / len(similar))
        if failure_rate > 0.5:
            risk = "high"
            risk_factors.append(f"{failure_rate:.0%} of similar directives had issues")
        elif failure_rate > 0.2:
            risk = "medium"
            risk_factors.append(f"{failure_rate:.0%} of similar directives had issues")

    if cost_estimate.get("predicted") and cost_estimate["predicted"] > 5.0:
        risk = "high" if risk != "high" else risk
        risk_factors.append(f"High estimated cost: ${cost_estimate['predicted']:.2f}")

    # Agent recommendations from outcomes of similar work
    agent_performance = _get_agent_performance_for_similar(similar)

    return {
        "similar_directives": similar,
        "cost_estimate": cost_estimate,
        "historical_average": {
            "avg_cost": round(avg_cost, 4),
            "avg_tasks": avg_tasks,
            "avg_duration_sec": round(avg_duration, 1),
        },
        "risk": risk,
        "risk_factors": risk_factors,
        "agent_recommendations": agent_performance,
        "has_precedent": len(similar) > 0,
    }


def format_briefing(analysis: dict) -> str:
    """Format the analysis into a human-readable briefing for Slack."""
    lines = []

    if analysis["has_precedent"]:
        lines.append("*Prior Art Found:*")
        for s in analysis["similar_directives"][:3]:
            similarity_pct = int(s["similarity"] * 100)
            cost_str = f"${s['total_cost']:.2f}" if s["total_cost"] > 0 else "n/a"
            lines.append(f"  - [{similarity_pct}% match] {s['directive_text'][:60]}... (cost: {cost_str})")

    cost_est = analysis["cost_estimate"]
    if cost_est.get("predicted"):
        lines.append(f"\n*Cost Estimate:* ${cost_est['predicted']:.2f} "
                     f"(range: ${cost_est['confidence_low']:.2f}–${cost_est['confidence_high']:.2f})")

    hist = analysis["historical_average"]
    if hist["avg_tasks"] > 0:
        lines.append(f"*Historical Average:* {hist['avg_tasks']} tasks, "
                     f"${hist['avg_cost']:.2f}, {hist['avg_duration_sec']/60:.0f}min")

    if analysis["risk_factors"]:
        lines.append(f"\n*Risk: {analysis['risk'].upper()}*")
        for rf in analysis["risk_factors"]:
            lines.append(f"  - {rf}")

    if analysis["agent_recommendations"]:
        lines.append("\n*Top Agents for This Type of Work:*")
        for agent, rate in list(analysis["agent_recommendations"].items())[:3]:
            lines.append(f"  - {agent}: {rate:.0%} success rate")

    return "\n".join(lines) if lines else "No historical data available yet."


def _get_agent_performance_for_similar(similar: list[dict]) -> dict[str, float]:
    """Look up which agents performed well on similar directive types."""
    if not similar:
        return {}

    # Get outcomes for similar directives
    agent_scores: dict[str, list[int]] = {}
    for s in similar:
        outcomes = ml_store.get_outcomes(limit=100)
        for o in outcomes:
            if o["directive_id"] == s["directive_id"]:
                aid = o["agent_id"]
                if aid not in agent_scores:
                    agent_scores[aid] = []
                agent_scores[aid].append(1 if o["outcome"] == "complete" else 0)

    # Compute success rates
    return {
        agent: sum(scores) / len(scores)
        for agent, scores in agent_scores.items()
        if len(scores) >= 2
    }
