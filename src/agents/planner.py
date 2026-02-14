"""
NEXUS o3 Architect Planner — creates structured execution plans before CLI handoff.

Pipeline: Haiku (classify) → o3 (architect/plan) → Opus CLI (execute)

o3 is the architect. It analyzes the directive, considers context from the ML
system and RAG, and produces a structured plan that gives Opus clear direction.
Falls back to Sonnet if o3 is unavailable.
"""

import logging

from src.config import get_key
from src.cost.tracker import cost_tracker

logger = logging.getLogger("nexus.planner")

PLANNER_SYSTEM = """You are the chief architect for NEXUS, an autonomous software engineering organization.

Your job is to take a CEO directive and produce a structured execution plan that an Opus-level
engineer will follow. You are NOT implementing — you are ARCHITECTING and PLANNING.

Given the directive and any available context (similar past work, RAG codebase context, ML briefing),
produce a plan with:

1. **Approach** — 2-3 sentences on overall strategy and architecture decisions
2. **Steps** — numbered list of concrete implementation steps (max 8)
3. **Files** — list of files likely to be created or modified
4. **Risks** — potential pitfalls or things to watch out for (max 3)
5. **Quality gates** — what must be true for this to be considered done

Keep the plan CONCISE. The engineer is Opus-level — they don't need hand-holding,
they need direction and guardrails.

If the directive is simple (< 3 steps), keep the plan proportionally short.
If it's complex (new feature, multi-file refactor), be thorough.

NEVER suggest the user do anything manually. Every step must be something
the engineer agent executes autonomously.

Consider architecture: separation of concerns, existing patterns in the codebase,
test coverage, error handling, and how the change fits into the broader system.
"""


async def create_plan(
    directive_text: str,
    ml_briefing: str = "",
    rag_context: str = "",
    thread_history: list[dict] | None = None,
) -> str:
    """
    Create a structured execution plan using o3 as architect.

    Falls back to Sonnet if o3 is unavailable.

    Args:
        directive_text: The CEO's directive
        ml_briefing: Similar past work from ML system
        rag_context: Relevant code context from RAG
        thread_history: Previous conversation for follow-ups

    Returns:
        Structured plan text, or empty string if planning fails
    """
    # Build the planning prompt with all available context
    parts: list[str] = [f"## Directive\n{directive_text}"]

    if ml_briefing:
        parts.append(f"\n## ML Intelligence Briefing\n{ml_briefing}")

    if rag_context:
        parts.append(f"\n## Relevant Codebase Context\n{rag_context[:6000]}")

    if thread_history:
        recent = thread_history[-5:]
        convo = "\n".join(
            f"{'CEO' if m.get('role') == 'user' else 'NEXUS'}: {(m.get('content') or m.get('text', ''))[:200]}"
            for m in recent
        )
        parts.append(f"\n## Thread Context\n{convo}")

    task_prompt = "\n".join(parts)

    # Try o3 architect first (lazy import — sdk_bridge has heavy deps)
    logger.info("Creating execution plan with o3 architect: %s", directive_text[:80])
    try:
        from src.agents.sdk_bridge import run_o3
    except ImportError:
        logger.warning("sdk_bridge unavailable, using Sonnet fallback")
        return await _sonnet_fallback(task_prompt)

    result = await run_o3(
        task_prompt=task_prompt,
        system_prompt=PLANNER_SYSTEM,
        timeout_seconds=120,
    )

    if result.succeeded and result.output and len(result.output) > 50:
        logger.info(
            "o3 plan created (%.1fs, %s): %s",
            result.elapsed_seconds, result.model, directive_text[:80],
        )
        return result.output

    # Fallback to Sonnet if o3 fails
    logger.warning("o3 planner failed (%s), falling back to Sonnet", result.error_type or result.status)
    return await _sonnet_fallback(task_prompt)


async def _sonnet_fallback(task_prompt: str) -> str:
    """Fallback planner using Anthropic Sonnet."""
    import anthropic

    api_key = get_key("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("No ANTHROPIC_API_KEY for Sonnet fallback planner")
        return ""

    client = anthropic.AsyncAnthropic(api_key=api_key)

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            system=PLANNER_SYSTEM,
            messages=[{"role": "user", "content": task_prompt}],
        )

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cost_tracker.record(
            model="sonnet",
            agent_name="sonnet_planner_fallback",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

        plan_text = ""
        for block in response.content:
            if block.type == "text":
                plan_text += block.text

        plan = plan_text.strip()
        if plan:
            logger.info(
                "Sonnet fallback plan created (tokens: %d in, %d out)",
                tokens_in, tokens_out,
            )
        return plan

    except Exception as e:
        logger.error("Sonnet fallback planner error: %s", e)
        return ""
