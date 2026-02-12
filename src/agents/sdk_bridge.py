"""
Agent SDK Bridge

Three execution modes for agents:
1. Claude Code CLI — spawns `claude --dangerously-skip-permissions` for
   implementation agents. Uses Max subscription ($0 API cost).
2. Claude Agent SDK — spawns SDK sessions for agents needing filesystem access.
3. Direct API — Gemini and o3 via LangChain.
"""

import asyncio
import logging
import os
import shutil
import time
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

logger = logging.getLogger("nexus.sdk_bridge")


from src.config import get_key as _load_key  # consolidated key loading

MODEL_MAP = {
    "opus": "opus",
    "sonnet": "sonnet",
    "haiku": "haiku",
}

# Claude Code CLI model flag mapping
CLI_MODEL_MAP = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-5-20250929",
    "haiku": "claude-haiku-4-5-20251001",
}


from src.cost.tracker import cost_tracker

# ---------------------------------------------------------------------------
# Claude Code CLI Bridge (Max subscription — $0 API cost)
# ---------------------------------------------------------------------------

async def run_claude_code(
    agent_name: str,
    agent_config: dict,
    task_prompt: str,
    project_path: str,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """
    Spawn a Claude Code CLI session in --dangerously-skip-permissions mode.
    Uses the Max subscription so API cost is $0. The CLI handles all tool
    use (file read/write, bash, grep, glob) autonomously.

    Falls back to Agent SDK if the CLI binary is not found.
    """
    claude_bin = shutil.which("claude")
    if not claude_bin:
        logger.warning(f"[{agent_name}] Claude CLI not found, falling back to SDK")
        return await run_sdk_agent(agent_name, agent_config, task_prompt, project_path)

    model_key = agent_config.get("model", "sonnet")
    model_id = CLI_MODEL_MAP.get(model_key, CLI_MODEL_MAP["sonnet"])
    system_prompt = agent_config.get("system_prompt", "")

    full_prompt = task_prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n---\n\nTASK:\n{task_prompt}"

    # Build argument list — no shell interpolation, safe from injection
    cmd = [
        claude_bin,
        "--dangerously-skip-permissions",
        "--model", model_id,
        "--output-format", "text",
        "--verbose",
        "-p", full_prompt,
    ]

    logger.info(f"[{agent_name}] Spawning Claude Code CLI ({model_id}) in {project_path}")
    start_time = time.time()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            elapsed = time.time() - start_time
            logger.error(f"[{agent_name}] Claude Code CLI timed out after {elapsed:.0f}s")
            return {
                "output": f"Claude Code CLI timed out after {timeout_seconds}s",
                "tokens_in": 0, "tokens_out": 0, "cost": 0.0,
                "model": f"claude-code:{model_id}", "agent": agent_name,
                "mode": "claude_code_cli", "elapsed_seconds": elapsed,
            }

        elapsed = time.time() - start_time
        output = stdout.decode("utf-8", errors="replace").strip()
        errors = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0 and not output:
            output = f"CLI exited with code {proc.returncode}: {errors[:1000]}"

        # Record $0 cost but track the event for analytics
        cost_tracker.record(
            model=f"claude-code:{model_key}",
            agent_name=agent_name,
            tokens_in=0, tokens_out=0,
            project=project_path,
        )

        logger.info(f"[{agent_name}] Claude Code CLI completed in {elapsed:.1f}s ({len(output)} chars)")

        return {
            "output": output,
            "tokens_in": 0, "tokens_out": 0, "cost": 0.0,
            "model": f"claude-code:{model_id}", "agent": agent_name,
            "mode": "claude_code_cli", "elapsed_seconds": elapsed,
        }

    except FileNotFoundError:
        logger.warning(f"[{agent_name}] Claude CLI binary not executable, falling back to SDK")
        return await run_sdk_agent(agent_name, agent_config, task_prompt, project_path)
    except Exception as e:
        logger.error(f"[{agent_name}] Claude Code CLI error: {e}")
        return {
            "output": f"Claude Code CLI error: {str(e)}",
            "tokens_in": 0, "tokens_out": 0, "cost": 0.0,
            "model": f"claude-code:{model_key}", "agent": agent_name,
            "mode": "claude_code_cli",
        }


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
    # Apply model downgrade if CFO enforcement active
    model = cost_tracker.get_effective_model(MODEL_MAP.get(agent_config.get("model", "sonnet"), "sonnet"))
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

    enforcement = cost_tracker.record(model, agent_name, tokens_in, tokens_out)
    if enforcement.get("alerts"):
        from src.slack.notifier import notify
        for alert in enforcement["alerts"]:
            notify(f"🏦 {alert}")
    cost = cost_tracker.calculate_cost(model, tokens_in, tokens_out)

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

    enforcement = cost_tracker.record(model, agent_name, tokens_in, tokens_out)
    if enforcement.get("alerts"):
        from src.slack.notifier import notify
        for alert in enforcement["alerts"]:
            notify(f"🏦 {alert}")
    cost = cost_tracker.calculate_cost(model, tokens_in, tokens_out)

    return {
        "output": "\n".join(output_parts),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost": cost,
        "model": model,
        "agent": agent_name,
    }
