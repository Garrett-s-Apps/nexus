"""
Agent SDK Bridge

Spawns Claude Agent SDK sessions for agents that need to interact with
the filesystem (write code, run bash, edit files, commit to git).

Also handles direct API calls for non-Anthropic models (Gemini, o3).
"""

import os
import asyncio
import time
from typing import Any
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


def _load_key(key_name: str) -> str | None:
    val = os.environ.get(key_name)
    if val:
        return val
    try:
        with open(os.path.expanduser("~/.nexus/.env.keys")) as f:
            for line in f:
                line = line.strip()
                if line.startswith(key_name + "="):
                    return line.split("=", 1)[1]
    except FileNotFoundError:
        pass
    return None


MODEL_MAP = {
    "opus": "opus",
    "sonnet": "sonnet",
    "haiku": "haiku",
}


class CostTracker:
    """Tracks token costs across all agent invocations."""

    PRICING = {
        "opus": {"input": 15.0, "output": 75.0},
        "sonnet": {"input": 3.0, "output": 15.0},
        "haiku": {"input": 0.25, "output": 1.25},
        "gemini": {"input": 1.25, "output": 5.0},
        "o3": {"input": 10.0, "output": 40.0},
    }

    def __init__(self):
        self.total_cost = 0.0
        self.by_model: dict[str, float] = {}
        self.by_agent: dict[str, float] = {}
        self.start_time = time.time()

    def record(self, model: str, agent_name: str, tokens_in: int, tokens_out: int):
        pricing = self.PRICING.get(model, {"input": 3.0, "output": 15.0})
        cost = (tokens_in / 1_000_000 * pricing["input"]) + (tokens_out / 1_000_000 * pricing["output"])
        self.total_cost += cost
        self.by_model[model] = self.by_model.get(model, 0.0) + cost
        self.by_agent[agent_name] = self.by_agent.get(agent_name, 0.0) + cost
        return cost

    @property
    def hourly_rate(self) -> float:
        elapsed_hours = (time.time() - self.start_time) / 3600
        if elapsed_hours < 0.001:
            return 0.0
        return self.total_cost / elapsed_hours

    @property
    def over_budget(self) -> bool:
        return self.hourly_rate > 1.0


cost_tracker = CostTracker()


async def run_sdk_agent(
    agent_name: str,
    agent_config: dict,
    task_prompt: str,
    project_path: str,
) -> dict[str, Any]:
    """
    Spawn a Claude Agent SDK session for an agent that needs filesystem access.
    Returns the agent's output and cost information.
    """
    model = MODEL_MAP.get(agent_config.get("model", "sonnet"), "sonnet")
    system_prompt = agent_config.get("system_prompt", "")
    allowed_tools = agent_config.get("tools", ["Read", "Grep", "Glob"])

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        permission_mode="acceptEdits",
        cwd=project_path,
        allowed_tools=allowed_tools,
        max_turns=50,
    )

    output_parts = []
    tokens_in = 0
    tokens_out = 0

    try:
        async for message in query(prompt=task_prompt, options=options):
            if hasattr(message, "content"):
                for block in message.content if isinstance(message.content, list) else [message.content]:
                    if hasattr(block, "text"):
                        output_parts.append(block.text)
            if hasattr(message, "usage"):
                tokens_in += getattr(message.usage, "input_tokens", 0)
                tokens_out += getattr(message.usage, "output_tokens", 0)
    except Exception as e:
        output_parts.append(f"Agent execution error: {str(e)}")

    cost = cost_tracker.record(model, agent_name, tokens_in, tokens_out)

    return {
        "output": "\n".join(output_parts),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost": cost,
        "model": model,
        "agent": agent_name,
    }


async def run_gemini(
    task_prompt: str,
    system_prompt: str = "",
    images: list[str] | None = None,
) -> dict[str, Any]:
    """Call Gemini for visual QA and multimodal tasks."""
    api_key = _load_key("GOOGLE_AI_API_KEY")
    if not api_key:
        return {"output": "ERROR: No Google AI API key found", "cost": 0.0}

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=api_key,
    )

    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=task_prompt))

    try:
        response = await llm.ainvoke(messages)
        cost = cost_tracker.record("gemini", "ux_consultant", 1000, 500)
        return {
            "output": response.content,
            "cost": cost,
            "model": "gemini",
            "agent": "ux_consultant",
        }
    except Exception as e:
        return {"output": f"Gemini error: {str(e)}", "cost": 0.0}


async def run_o3(
    task_prompt: str,
    system_prompt: str = "",
) -> dict[str, Any]:
    """Call OpenAI o3 for systems architecture consulting."""
    api_key = _load_key("OPENAI_API_KEY")
    if not api_key:
        return {"output": "ERROR: No OpenAI API key found", "cost": 0.0}

    llm = ChatOpenAI(
        model="o3",
        api_key=api_key,
    )

    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=task_prompt))

    try:
        response = await llm.ainvoke(messages)
        cost = cost_tracker.record("o3", "systems_consultant", 2000, 1000)
        return {
            "output": response.content,
            "cost": cost,
            "model": "o3",
            "agent": "systems_consultant",
        }
    except Exception as e:
        return {"output": f"o3 error: {str(e)}", "cost": 0.0}


async def run_planning_agent(
    agent_name: str,
    agent_config: dict,
    task_prompt: str,
    context: str = "",
) -> dict[str, Any]:
    """
    Run a planning-only agent (no filesystem access needed).
    Uses the Agent SDK but with read-only tools.
    """
    model = MODEL_MAP.get(agent_config.get("model", "sonnet"), "sonnet")
    system_prompt = agent_config.get("system_prompt", "")

    full_prompt = task_prompt
    if context:
        full_prompt = f"CONTEXT:\n{context}\n\nTASK:\n{task_prompt}"

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        permission_mode="plan",
        max_turns=10,
    )

    output_parts = []
    tokens_in = 0
    tokens_out = 0

    try:
        async for message in query(prompt=full_prompt, options=options):
            if hasattr(message, "content"):
                for block in message.content if isinstance(message.content, list) else [message.content]:
                    if hasattr(block, "text"):
                        output_parts.append(block.text)
            if hasattr(message, "usage"):
                tokens_in += getattr(message.usage, "input_tokens", 0)
                tokens_out += getattr(message.usage, "output_tokens", 0)
    except Exception as e:
        output_parts.append(f"Planning agent error: {str(e)}")

    cost = cost_tracker.record(model, agent_name, tokens_in, tokens_out)

    return {
        "output": "\n".join(output_parts),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost": cost,
        "model": model,
        "agent": agent_name,
    }
