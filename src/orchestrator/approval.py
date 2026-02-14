"""
User Approval Gates for Strategic Transitions

Provides interactive approval prompts for critical decision points where
the USER (Garrett) must approve before the system proceeds autonomously.

This ensures human oversight on:
- Strategic transitions (Spec → Dev, Analysis → Dev)
- Budget thresholds (>$50)
- Major architectural decisions
- Rebuild operations
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def request_user_approval(
    title: str,
    context: dict[str, Any],
    timeout_seconds: int = 300
) -> bool:
    """
    Request approval from the user (Garrett).

    Displays:
    - What decision is being made
    - Why it matters
    - Cost implications
    - Risk if approved/rejected

    Args:
        title: The approval decision being requested
        context: Dictionary containing description, cost, risk, and optional fields
        timeout_seconds: How long to wait for user input (default: 5 minutes)

    Returns:
        True if approved, False if rejected

    Example:
        >>> approved = await request_user_approval(
        ...     "Spec → Development Transition",
        ...     {
        ...         "description": "Proceed with development of feature X",
        ...         "cost": "Estimated $25.00",
        ...         "risk": "Development will begin immediately after approval",
        ...     }
        ... )
    """

    print("\n" + "="*60)
    print(f"🔔 APPROVAL REQUIRED: {title}")
    print("="*60)
    print(f"\nContext: {context.get('description', 'N/A')}")
    print(f"Cost Impact: {context.get('cost', 'N/A')}")
    print(f"Risk: {context.get('risk', 'None')}")

    # Optional fields
    if 'requester' in context:
        print(f"Requested By: {context['requester']}")
    if 'severity' in context:
        print(f"Severity: {context['severity']}")

    print("\n" + "-"*60)
    print("Options:")
    print("  [A] Approve - Proceed with this decision")
    print("  [R] Reject - Block this decision and halt")
    print("  [C] Request Changes - Reject with feedback")
    print("-"*60)

    # Create async task for user input with timeout
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(_get_user_input, "\nYour decision (A/R/C): "),
            timeout=timeout_seconds
        )

        response = response.strip().upper()

        if response == "A":
            logger.info("User APPROVED: %s", title)
            print("✅ APPROVED - Proceeding...")
            return True
        elif response == "R":
            logger.warning("User REJECTED: %s", title)
            print("❌ REJECTED - Halting...")
            return False
        elif response == "C":
            logger.warning("User requested CHANGES: %s", title)
            print("🔄 CHANGES REQUESTED - Halting for revision...")
            feedback = await asyncio.to_thread(
                _get_user_input,
                "Please describe requested changes: "
            )
            logger.info("User feedback for %s: %s", title, feedback)
            return False
        else:
            logger.warning("Invalid user response '%s' for %s, defaulting to REJECT", response, title)
            print("⚠️  Invalid response - defaulting to REJECT")
            return False

    except asyncio.TimeoutError:
        logger.error("User approval timeout for %s after %ds, defaulting to REJECT", title, timeout_seconds)
        print(f"\n⏱️  Approval timeout after {timeout_seconds}s - defaulting to REJECT")
        return False


def _get_user_input(prompt: str) -> str:
    """Wrapper for input() to support async execution."""
    return input(prompt)


async def request_budget_approval(
    total_budget: float,
    breakdown: dict[str, float],
    threshold: float = 50.0
) -> bool:
    """
    Request user approval for high-budget operations.

    Args:
        total_budget: Total budget in USD
        breakdown: Budget breakdown by category
        threshold: Budget threshold requiring approval (default: $50)

    Returns:
        True if approved or below threshold, False if rejected
    """
    if total_budget <= threshold:
        logger.info("Budget $%.2f below threshold $%.2f, auto-approved", total_budget, threshold)
        return True

    breakdown_str = "\n".join(
        f"  - {key}: ${value:.2f}" for key, value in breakdown.items()
    )

    return await request_user_approval(
        "High Budget Approval",
        {
            "description": f"This project will cost ${total_budget:.2f}\n\nBreakdown:\n{breakdown_str}",
            "cost": f"${total_budget:.2f}",
            "risk": "High cost project - ensure ROI justifies spend",
            "severity": "High" if total_budget > 100 else "Medium",
        }
    )


async def request_spec_to_dev_approval(
    spec_summary: str,
    estimated_cost: float,
    acceptance_criteria: list[str]
) -> bool:
    """
    Request user approval for Spec → Development transition.

    Args:
        spec_summary: Summary of the specification (first 500 chars)
        estimated_cost: Estimated development cost in USD
        acceptance_criteria: List of acceptance criteria

    Returns:
        True if approved, False if rejected
    """
    criteria_str = "\n".join(f"  - {c}" for c in acceptance_criteria[:5])
    if len(acceptance_criteria) > 5:
        criteria_str += f"\n  ... and {len(acceptance_criteria) - 5} more"

    return await request_user_approval(
        "Spec → Development Transition",
        {
            "description": f"Proceed with development of:\n\n{spec_summary}\n\nAcceptance Criteria:\n{criteria_str}",
            "cost": f"Estimated ${estimated_cost:.2f}",
            "risk": "Development will begin immediately after approval. Code changes will be made to the project.",
            "requester": "CEO (after spec review)",
            "severity": "Critical",
        }
    )


async def request_analysis_to_dev_approval(
    analysis_summary: str,
    findings_count: int,
    estimated_effort: str
) -> bool:
    """
    Request user approval for Analysis → Development transition.

    Args:
        analysis_summary: Summary of analysis findings
        findings_count: Number of findings identified
        estimated_effort: Estimated effort (e.g., "20-40 hours")

    Returns:
        True if approved, False if rejected
    """
    return await request_user_approval(
        "Analysis → Development Transition",
        {
            "description": f"Analysis complete with {findings_count} findings.\n\n{analysis_summary}\n\nProceed with implementation?",
            "cost": f"Estimated effort: {estimated_effort}",
            "risk": "Will make changes to existing codebase based on analysis findings",
            "requester": "Chief Architect",
            "severity": "High",
        }
    )


async def request_rebuild_start_approval(
    project_path: str,
    estimated_cost: str = "Analysis: ~$2-5, Implementation: TBD"
) -> bool:
    """
    Request user approval before starting rebuild analysis.

    Args:
        project_path: Path to project being analyzed
        estimated_cost: Estimated cost string

    Returns:
        True if approved, False if rejected
    """
    return await request_user_approval(
        "Start Rebuild Analysis",
        {
            "description": f"Analyze codebase at:\n{project_path}\n\nfor modernization opportunities",
            "cost": estimated_cost,
            "risk": "Will identify technical debt and required changes. No code modifications during analysis.",
            "requester": "User (via rebuild command)",
            "severity": "Medium",
        }
    )


async def request_architectural_decision_approval(
    decision_title: str,
    decision_details: str,
    impact: str,
    alternatives: list[str] | None = None
) -> bool:
    """
    Request user approval for major architectural decisions.

    Args:
        decision_title: Short title of the architectural decision
        decision_details: Detailed explanation of the decision
        impact: Impact description
        alternatives: List of alternative approaches considered

    Returns:
        True if approved, False if rejected
    """
    description = f"{decision_details}\n\nImpact:\n{impact}"

    if alternatives:
        alt_str = "\n".join(f"  - {alt}" for alt in alternatives)
        description += f"\n\nAlternatives Considered:\n{alt_str}"

    return await request_user_approval(
        f"Architectural Decision: {decision_title}",
        {
            "description": description,
            "cost": "N/A (strategic decision)",
            "risk": "This decision will affect system architecture and may be difficult to reverse",
            "requester": "Chief Architect",
            "severity": "Critical",
        }
    )
