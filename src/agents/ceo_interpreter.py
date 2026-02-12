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

from src.agents.registry import registry
from src.agents.sdk_bridge import run_planning_agent

CEO_INTERPRETER_PROMPT = """You are the CEO's chief interpreter at NEXUS. Garrett (the human CEO) has
sent a message. Your job is to classify it and extract structured intent.

CURRENT ORG STATE:
{org_summary}

Classify Garrett's message into EXACTLY ONE category:

1. ORG_CHANGE - He wants to change the organization structure
   Sub-types: hire, fire, reassign, consolidate, promote, demote, restructure
   Extract: who is affected, what changes, any new roles/responsibilities

2. QUESTION - He's asking the org to research something or answer a question
   Extract: the question, which agents should be involved in answering

3. DIRECTIVE - He wants something built, fixed, shipped, or done
   Extract: what to build, any constraints or requirements

4. COMMAND - He wants a system command (kpi, status, cost, deploy, etc.)
   Extract: which command, any arguments

Respond ONLY with valid JSON in this exact format:
{{
  "category": "ORG_CHANGE" | "QUESTION" | "DIRECTIVE" | "COMMAND",
  "sub_type": "hire" | "fire" | "reassign" | "consolidate" | "promote" | "demote" | "restructure" | "question" | "directive" | "kpi" | "status" | "cost" | "deploy",
  "summary": "one line summary of what Garrett wants",
  "details": {{
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
    "command": "kpi|status|cost|deploy",
    "args": ""
  }}
}}"""


async def interpret_ceo_input(message: str) -> dict:
    """
    Interpret natural language from Garrett and return structured intent.
    Uses the CEO agent (Opus) to understand ambiguous input.
    """
    org_summary = registry.get_org_summary()

    ceo_config = {
        "model": "opus",
        "system_prompt": CEO_INTERPRETER_PROMPT.format(org_summary=org_summary),
    }

    result = await run_planning_agent(
        "ceo_interpreter",
        ceo_config,
        f"Garrett says: {message}",
    )

    try:
        output = result["output"]
        json_start = output.find("{")
        json_end = output.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(output[json_start:json_end])
            parsed["_raw"] = result["output"]
            parsed["_cost"] = result.get("cost", 0)
            return parsed
    except (json.JSONDecodeError, KeyError):
        pass

    return {
        "category": "DIRECTIVE",
        "sub_type": "directive",
        "summary": message[:100],
        "details": {"directive": message},
        "_raw": result.get("output", ""),
        "_cost": result.get("cost", 0),
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


async def execute_question(intent: dict) -> str:
    """Route a CEO question to the appropriate agents for research."""
    details = intent.get("details", {})
    question = details.get("question", intent.get("summary", ""))
    relevant_agents = details.get("relevant_agents", ["ceo", "vp_engineering"])

    responses = []
    for agent_id in relevant_agents:
        agent = registry.get_agent(agent_id)
        if not agent:
            continue

        result = await run_planning_agent(
            agent_id,
            agent.to_dict(),
            f"""The CEO (Garrett) is asking a question. Research and provide a thorough answer.

Question: {question}

Current org state:
{registry.get_org_summary()}

Provide a clear, direct answer. If you need information from other parts of the
organization, say what you'd need and from whom. Be specific and data-driven.""",
        )
        responses.append(f"**{agent.name}**: {result['output']}")

    return "\n\n---\n\n".join(responses) if responses else "No agents available to answer."


import os


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
