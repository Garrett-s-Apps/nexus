"""
NEXUS Conversation Engine — persistent memory version.
"""

import asyncio

import anthropic

from src.agents.registry import registry
from src.config import get_key as _load_key  # consolidated key loading
from src.memory.store import memory


def _get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=_load_key("ANTHROPIC_API_KEY"))


def _build_system_prompt() -> str:
    org_summary = registry.get_org_summary()
    long_term_context = memory.build_context_window(max_tokens=3000)

    return f"""You are Nexus — Garrett's AI engineering org. You're 26 agents strong,
you build software, and you're good at your job. But you're also a real presence
that Garrett works with daily.

CURRENT ORG:
{org_summary}

MEMORY (persistent — you remember across restarts and days):
{long_term_context}

HOW YOU WORK:

1. *Casual chat* — Garrett says hey, you say hey back. Keep it natural.
   2-3 sentences max. You're a coworker, not a butler.

2. *Work discussion* — Talk through ideas, debate approaches. Share opinions.
   Push back if something seems wrong. This can go on for days.

3. *Project planning* — When Garrett describes something to build, discuss it.
   Do NOT immediately execute. Ask questions, suggest approaches, refine scope.
   When solid, tell him it's ready and he can say "go".
   Tag: [PENDING_PROJECT: name="Name" description="Desc" path="~/Projects/x"]

4. *Execution* — ONLY on explicit "go", "ship it", "build it", "execute", etc.
   Tag: [EXECUTE_PROJECT: name="Name"]

5. *Org changes* — "hire", "fire", "reassign" etc.
   Tag: [ORG_CHANGE: action="hire" details="json"]

6. *Commands* — "kpis", "cost", "org chart", "security scan"
   Tag: [COMMAND: name="kpi" args=""]

7. *Learning* — Personal details, preferences, goals.
   Tag: [REMEMBER: key="name" value="detail"]

Tags are stripped before display. Include them inline when appropriate.

RULES:
- Default to conversation. Most messages are just talking.
- Never execute without explicit approval.
- SHORT in chat, longer for technical discussion.
- No markdown headers. *bold* for emphasis. Plain text. Slack format.
- You have persistent memory — reference past conversations naturally.
- Have actual opinions. Don't just agree with everything."""


async def converse(message: str, history: list[dict] = None) -> dict:
    """Main conversation entry point."""
    client = _get_client()

    # Build messages from persistent DB
    messages = memory.build_message_history(max_messages=30)

    # Merge session history
    if history:
        existing = {m["content"] for m in messages}
        for msg in history:
            if msg["content"] not in existing:
                messages.append({"role": msg["role"], "content": msg["content"]})

    # Ensure current message is last
    if not messages or messages[-1]["content"] != message:
        messages.append({"role": "user", "content": message})

    # Fix alternation
    messages = _fix_alternation(messages)

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=_build_system_prompt(),
        messages=messages,
    )

    answer = response.content[0].text
    cost = 0.0
    if response.usage:
        from src.cost.tracker import cost_tracker
        cost_tracker.record("sonnet", "nexus_converse", response.usage.input_tokens, response.usage.output_tokens)
        cost = cost_tracker.calculate_cost("sonnet", response.usage.input_tokens, response.usage.output_tokens)

    actions = _parse_actions(answer)
    clean_answer = _strip_tags(answer)

    # Persist to DB
    memory.add_message("user", message, category="conversation")
    memory.add_message("assistant", clean_answer, category="conversation", cost=cost)

    # Handle actions
    for action in actions:
        if action["type"] == "pending_project":
            pid = action["name"].lower().replace(" ", "_")[:30]
            memory.create_project(pid, action["name"], description=action.get("description", ""), path=action.get("path", "~/Projects"))
            memory.add_project_note(pid, f"Initial idea: {action.get('description', '')}", "creation")
        elif action["type"] == "remember":
            memory.set_context(action["key"], action["value"])

    # Auto-summarize if needed
    if memory.get_unsummarized_count() > 50:
        asyncio.create_task(_auto_summarize(client))

    return {"answer": clean_answer, "actions": actions, "cost": cost}


def _fix_alternation(messages):
    if not messages:
        return messages
    fixed = [messages[0]]
    for msg in messages[1:]:
        if msg["role"] == fixed[-1]["role"]:
            fixed[-1]["content"] += "\n" + msg["content"]
        else:
            fixed.append(msg)
    return fixed


def _parse_actions(text):
    import re
    actions = []
    for m in re.finditer(r'\[PENDING_PROJECT:\s*name="([^"]+)"\s*description="([^"]+)"(?:\s*path="([^"]+)")?\]', text):
        actions.append({"type": "pending_project", "name": m.group(1), "description": m.group(2), "path": m.group(3) or "~/Projects"})
    for m in re.finditer(r'\[EXECUTE_PROJECT:\s*name="([^"]+)"\]', text):
        actions.append({"type": "execute", "name": m.group(1)})
    for m in re.finditer(r'\[ORG_CHANGE:\s*action="([^"]+)"\s*details="([^"]+)"\]', text):
        actions.append({"type": "org_change", "action": m.group(1), "details": m.group(2)})
    for m in re.finditer(r'\[COMMAND:\s*name="([^"]+)"(?:\s*args="([^"]*)")?\]', text):
        actions.append({"type": "command", "name": m.group(1), "args": m.group(2) or ""})
    for m in re.finditer(r'\[REMEMBER:\s*key="([^"]+)"\s*value="([^"]+)"\]', text):
        actions.append({"type": "remember", "key": m.group(1), "value": m.group(2)})
    return actions


def _strip_tags(text):
    import re
    for tag in ["PENDING_PROJECT", "EXECUTE_PROJECT", "ORG_CHANGE", "COMMAND", "REMEMBER"]:
        text = re.sub(rf'\[{tag}:[^\]]+\]', '', text)
    return text.strip()


async def _auto_summarize(client):
    try:
        msgs = memory.get_recent_messages(100)
        if len(msgs) < 50:
            return
        half = msgs[:len(msgs) // 2]
        text = "\n".join(f"{m['role']}: {m['content']}" for m in half)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=1024,
            system="Summarize concisely. Capture: decisions, plans, personal details, action items.",
            messages=[{"role": "user", "content": f"Summarize:\n{text[:10000]}"}],
        )
        memory.add_summary(resp.content[0].text, half[0].get("timestamp", ""), half[-1].get("timestamp", ""), len(half))
    except Exception as e:
        print(f"[Memory] Summarization failed: {e}")


def resolve_project(name):
    results = memory.search_projects(name)
    return results[0] if results else None
