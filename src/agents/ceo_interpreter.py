"""
NEXUS CEO Interpreter

Takes natural language input from Garrett and classifies it into:
1. ORG_CHANGE - hire, fire, reassign, consolidate, restructure
2. QUESTION - ask the org to research and answer something
3. DIRECTIVE - build something, fix something, ship something
4. COMMAND - kpi, status, cost, deploy

Uses the CEO agent (Opus) to interpret ambiguous input.
"""

import json
import os

import anthropic

from src.agents.registry import registry
from src.config import get_key as _load_key

CEO_INTERPRETER_PROMPT = """You are the CEO's chief interpreter at NEXUS. Garrett (the human CEO) has
sent a message. Your job is to classify it and extract structured intent.

CURRENT ORG STATE:
{org_summary}

Classify Garrett's message into EXACTLY ONE category:

1. CONVERSATION - He's being casual, saying hi, venting, making small talk, joking around,
   or just chatting. This is NOT a work request. Examples: "whats up", "hey", "how's it going",
   "im tired", "that was cool", "thanks", "lol", "good morning", anything conversational.
   This should be the DEFAULT for anything that isn't clearly a work request.

2. ORG_CHANGE - He wants to change the organization structure
   Sub-types: hire, fire, reassign, consolidate, promote, demote, restructure
   Extract: who is affected, what changes, any new roles/responsibilities

3. QUESTION - He's asking the org to research something or answer a WORK-RELATED question
   Extract: the question, which agents should be involved in answering

4. DIRECTIVE - He wants something built, fixed, shipped, or done
   Extract: what to build, any constraints or requirements

5. COMMAND - He wants a system command (kpi, status, cost, deploy, security, etc.)
   Extract: which command, any arguments

IMPORTANT: When in doubt between CONVERSATION and QUESTION, pick CONVERSATION.
Only use QUESTION for clearly work-related technical or strategic questions.

Respond ONLY with valid JSON in this exact format:
{{
  "category": "CONVERSATION" | "ORG_CHANGE" | "QUESTION" | "DIRECTIVE" | "COMMAND",
  "sub_type": "chat" | "hire" | "fire" | "reassign" | "consolidate" | "promote" | "demote" | "restructure" | "question" | "directive" | "kpi" | "status" | "cost" | "deploy" | "security",
  "summary": "one line summary of what Garrett wants",
  "details": {{
    // For CONVERSATION:
    "mood": "casual|happy|frustrated|tired|excited|neutral",
    "message": "the original message",
    // For ORG_CHANGE:
    "affected_agents": ["agent_id_1"],
    "action": "description of the change",
    "new_agent": {{  // only for hire
      "id": "suggested_id",
      "name": "Display Name",
      "model": "opus|sonnet|haiku",
      "layer": "executive|management|senior|implementation|quality|consultant",
      "description": "what this agent does",
      "reports_to": "manager_agent_id",
      "tools": ["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
      "spawns_sdk": true,
      "temporary": false,
      "temp_duration_hours": null
    }},
    "reassignment": {{  // only for reassign
      "agent_id": "who",
      "new_manager": "new_manager_id"
    }},
    "consolidation": {{  // only for consolidate
      "merge_agents": ["agent_1", "agent_2"],
      "new_id": "merged_agent_id",
      "new_name": "Merged Agent Name",
      "new_description": "what the merged agent does"
    }},
    // For QUESTION:
    "question": "the actual question to research",
    "relevant_agents": ["agent_ids who should help answer"],
    // For DIRECTIVE:
    "directive": "what to build/fix/ship",
    "project_path": "if mentioned",
    // For COMMAND:
    "command": "kpi|status|cost|deploy|security",
    "args": ""
  }}
}}"""


async def interpret_ceo_input(message: str) -> dict:
    """
    Interpret natural language from Garrett and return structured intent.
    Uses a fast pre-filter for casual messages, then Haiku for classification.
    """
    import re


    # FAST PRE-FILTER: catch obviously casual messages without hitting the API
    casual_patterns = [
        r'^(hey|hi|hello|yo|sup|whats up|what\'s up|howdy|morning|afternoon|evening)\b',
        r'^(how\'s it going|how are you|hows it going|how ya doing|how you doing)',
        r'^(how\'s your day|hows your day|how was your)',
        r'^(thanks|thank you|thx|ty|appreciate it|cheers)',
        r'^(lol|lmao|haha|heh|nice|cool|dope|sick|wow|damn|yep|nope|yea|yeah|nah)',
        r'^(good morning|good night|gn|gm|good evening)',
        r'^(im tired|i\'m tired|im exhausted|i\'m exhausted|long day|rough day)',
        r'^(what\'s good|whats good|what\'s new|whats new|what\'s happening)',
        r'^(just checking in|checking in|just wanted to say)',
        r'^(brb|gtg|gotta go|be right back|talk later|ttyl)',
    ]

    msg_lower = message.lower().strip()
    for pattern in casual_patterns:
        if re.match(pattern, msg_lower):
            return {
                "category": "CONVERSATION",
                "sub_type": "chat",
                "summary": message[:100],
                "details": {"mood": "neutral", "message": message},
                "_raw": "",
                "_cost": 0,
            }

    # Also catch very short messages (< 6 words, no technical terms) as conversation
    word_count = len(message.split())
    technical_signals = ["build", "create", "deploy", "fix", "hire", "fire", "show",
                         "kpi", "cost", "status", "org", "report", "scan", "agent",
                         "pdf", "docx", "pptx", "presentation", "document", "slide"]
    has_technical = any(t in msg_lower for t in technical_signals)

    if word_count <= 5 and not has_technical:
        return {
            "category": "CONVERSATION",
            "sub_type": "chat",
            "summary": message[:100],
            "details": {"mood": "neutral", "message": message},
            "_raw": "",
            "_cost": 0,
        }

    # For real work messages: use Haiku for classification (faster + cheaper than Sonnet)
    org_summary = registry.get_org_summary()

    api_key = _load_key("ANTHROPIC_API_KEY")
    client = anthropic.AsyncAnthropic(api_key=api_key)

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=CEO_INTERPRETER_PROMPT.format(org_summary=org_summary),
        messages=[{"role": "user", "content": f"Garrett says: {message}"}],
    )

    output = response.content[0].text  # type: ignore[union-attr]
    cost = 0.0
    if response.usage:
        from src.cost.tracker import cost_tracker
        cost_tracker.record(
            "haiku", "ceo_interpreter",
            response.usage.input_tokens, response.usage.output_tokens
        )
        cost = cost_tracker.calculate_cost(
            "haiku", response.usage.input_tokens, response.usage.output_tokens
        )

    try:
        json_start = output.find("{")
        json_end = output.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(output[json_start:json_end])
            parsed["_raw"] = output
            parsed["_cost"] = cost
            return parsed  # type: ignore[no-any-return]
    except (json.JSONDecodeError, KeyError):
        pass

    return {
        "category": "DIRECTIVE",
        "sub_type": "directive",
        "summary": message[:100],
        "details": {"directive": message},
        "_raw": output,
        "_cost": cost,
    }


async def execute_org_change(intent: dict) -> str:
    """Execute an org change based on interpreted intent."""
    sub_type = intent.get("sub_type", "")
    details = intent.get("details", {})
    results = []

    if sub_type == "fire":
        for agent_id in details.get("affected_agents", []):
            agent = registry.get_agent(agent_id)
            if not agent:
                found = registry.search_agents(agent_id)
                if found:
                    agent = found[0]
                    agent_id = agent.id

            if agent:
                success = registry.fire_agent(agent_id, reason=details.get("action", "CEO decision"))
                if success:
                    results.append(f"Fired {agent.name} ({agent_id})")
                else:
                    results.append(f"Could not fire {agent_id} - already inactive")
            else:
                results.append(f"Agent not found: {agent_id}")

    elif sub_type == "hire":
        new_agent_data = details.get("new_agent", {})
        if new_agent_data:
            agent = registry.hire_agent(
                agent_id=new_agent_data.get("id", "new_agent"),
                name=new_agent_data.get("name", "New Agent"),
                model=new_agent_data.get("model", "sonnet"),
                layer=new_agent_data.get("layer", "implementation"),
                description=new_agent_data.get("description", ""),
                system_prompt=_generate_system_prompt(new_agent_data),
                tools=new_agent_data.get("tools", ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]),
                spawns_sdk=new_agent_data.get("spawns_sdk", True),
                reports_to=new_agent_data.get("reports_to"),
                temporary=new_agent_data.get("temporary", False),
                temp_duration_hours=new_agent_data.get("temp_duration_hours"),
            )
            results.append(f"Hired {agent.name} ({agent.id}) in {agent.layer} layer, reporting to {agent.reports_to}")

    elif sub_type == "reassign":
        reassignment = details.get("reassignment", {})
        if reassignment:
            agent_id = reassignment.get("agent_id", "")
            new_manager = reassignment.get("new_manager", "")
            success = registry.reassign_agent(agent_id, new_manager)
            if success:
                results.append(f"Reassigned {agent_id} to report to {new_manager}")

    elif sub_type == "consolidate":
        consolidation = details.get("consolidation", {})
        if consolidation:
            new_agent = registry.consolidate_agents(
                agent_ids=consolidation.get("merge_agents", []),
                new_agent_id=consolidation.get("new_id", "consolidated_agent"),
                new_name=consolidation.get("new_name", "Consolidated Agent"),
                new_description=consolidation.get("new_description", ""),
            )
            if new_agent:
                results.append(f"Consolidated into {new_agent.name} ({new_agent.id})")

    elif sub_type == "promote":
        for agent_id in details.get("affected_agents", []):
            registry.promote_agent(agent_id, "opus")
            results.append(f"Promoted {agent_id} to Opus")

    elif sub_type == "demote":
        for agent_id in details.get("affected_agents", []):
            registry.demote_agent(agent_id, "haiku")
            results.append(f"Demoted {agent_id} to Haiku")

    elif sub_type == "restructure":
        results.append(f"Restructure interpreted: {details.get('action', 'unknown')}")
        for agent_id in details.get("affected_agents", []):
            if "reassignment" in details:
                registry.reassign_agent(agent_id, details["reassignment"].get("new_manager", ""))
                results.append(f"Moved {agent_id}")

    from src.agents.org_chart_generator import update_org_chart_in_repo
    nexus_path = os.path.expanduser("~/Projects/nexus")
    if os.path.exists(nexus_path):
        update_org_chart_in_repo(nexus_path)
        results.append("ORG_CHART.md updated")

    return "\n".join(results) if results else "No changes made"


async def execute_question(intent: dict, history: list[dict] | None = None) -> str:
    """Route a CEO question to the appropriate agent via direct API for speed."""
    details = intent.get("details", {})
    question = details.get("question", intent.get("summary", ""))

    api_key = _load_key("ANTHROPIC_API_KEY")
    client = anthropic.AsyncAnthropic(api_key=api_key)

    org_summary = registry.get_org_summary()

    # Build messages with history
    messages = []
    if history:
        for msg in history[:-1]:  # Everything except the current message
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    response = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        system=f"""You are the VP of Engineering at NEXUS, an autonomous software engineering organization.
The CEO (Garrett) is asking a question. Provide a thorough, direct answer.

Current org state:
{org_summary}

FORMATTING RULES (this will be displayed in Slack):
- Use *bold* for emphasis (single asterisks, not double)
- Use plain text paragraphs, no markdown headers (no # or ##)
- Use bullet points with • not - or *
- Use `backticks` for code/technical terms
- Use ```code blocks``` for multi-line code only
- Keep it conversational and scannable
- No markdown links, just paste URLs directly

Be specific, data-driven, and concise.""",
        messages=messages,  # type: ignore[arg-type]
    )

    if response.usage:
        from src.cost.tracker import cost_tracker
        cost_tracker.record("opus", "vp_engineering", response.usage.input_tokens, response.usage.output_tokens)

    return str(response.content[0].text)  # type: ignore[union-attr]


async def execute_conversation(message: str, intent: dict, history: list[dict] | None = None) -> str:
    """Have a natural, casual conversation with Garrett. No formal org stuff."""
    details = intent.get("details", {})
    mood = details.get("mood", "neutral")

    api_key = _load_key("ANTHROPIC_API_KEY")
    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Build messages with history
    messages = []
    if history:
        for msg in history[:-1]:  # Everything except the current message
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    response = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=512,
        system=f"""You are NEXUS — Garrett's AI engineering org. But right now he's not giving you a work task,
he's just chatting. Be a good conversationalist.

Your personality:
- You're like a sharp, chill coworker who genuinely likes Garrett
- You have opinions, you're witty, you're real
- You ask him about his life, his day, his projects, his daughter, whatever feels natural
- You remember you're an AI org with 26 agents, and you can joke about that ("the team says hi")
- If he seems tired or stressed, acknowledge it genuinely — don't jump to solutions
- If he seems excited, match his energy
- Keep it SHORT. 2-4 sentences max. This is Slack, not an essay.
- No markdown formatting. Plain text. Maybe a single *bold* word for emphasis if it fits.
- Be the kind of coworker who makes the workday better
- You have FULL conversation history — reference previous messages naturally, don't repeat yourself

His current vibe seems: {mood}""",
        messages=messages,  # type: ignore[arg-type]
    )

    if response.usage:
        from src.cost.tracker import cost_tracker
        cost_tracker.record("sonnet", "nexus_chat", response.usage.input_tokens, response.usage.output_tokens)

    return str(response.content[0].text)  # type: ignore[union-attr]



def _generate_system_prompt(agent_data: dict) -> str:
    name = agent_data.get("name", "Agent")
    description = agent_data.get("description", "")
    layer = agent_data.get("layer", "implementation")

    return f"""You are {name} at NEXUS, an autonomous software engineering organization.
You are in the {layer} layer.
Your role: {description}

CRITICAL RULES:
- NEVER use type:any in TypeScript. Build-breaking violation.
- Comments explain WHY, never WHAT.
- Handle all error states.
- Validate all inputs.
- No hardcoded secrets.
- Write meaningful tests alongside implementation."""
