"""
NEXUS Sonnet Planner — creates structured execution plans before CLI handoff.

Sits between Haiku intake (classification) and Opus CLI (execution).
Sonnet analyzes the directive, considers context, and produces a plan
that gives Opus clear direction instead of a raw user message.
"""

import logging

import anthropic

from src.config import get_key
from src.cost.tracker import cost_tracker

logger = logging.getLogger("nexus.planner")

PLANNER_SYSTEM = """You are a senior engineering planner for NEXUS, an autonomous software engineering organization.

Your job is to take a CEO directive and produce a structured execution plan that an Opus-level
engineer will follow. You are NOT implementing — you are PLANNING.

Given the directive and any available context (similar past work, RAG codebase context, ML briefing),
produce a plan with:

1. **Approach** — 2-3 sentences on overall strategy
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
"""


async def create_plan(
    directive_text: str,
    ml_briefing: str = "",
    rag_context: str = "",
    thread_history: list[dict] | None = None,
) -> str:
    """
    Create a structured execution plan for a directive.

    Args:
        directive_text: The CEO's directive
        ml_briefing: Similar past work from ML system
        rag_context: Relevant code context from RAG
        thread_history: Previous conversation for follow-ups

    Returns:
        Structured plan text, or empty string if planning fails
    """
    api_key = get_key("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("No ANTHROPIC_API_KEY for planner")
        return ""

    client = anthropic.AsyncAnthropic(api_key=api_key)

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

    user_message = "\n".join(parts)

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            system=PLANNER_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cost_tracker.record(
            model="sonnet",
            agent_name="sonnet_planner",
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
                "Plan created for directive (tokens: %d in, %d out): %s",
                tokens_in, tokens_out, directive_text[:80],
            )
        return plan

    except anthropic.APIError as e:
        logger.error("Planner API error: %s", e)
        return ""
    except Exception as e:
        logger.exception("Planner unexpected error: %s", e)
        return ""
