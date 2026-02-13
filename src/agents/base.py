"""
NEXUS Agent Base Class

Self-orchestrating agents in a virtual company. Each agent reads the world state,
decides if it should act based on its role, and executes work autonomously.
Teams self-organize scrum-style. Leaders set direction and unblock.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from src.agents.org_chart import (
    ALL_AGENT_IDS,
    HAIKU,
    MODEL_COSTS,
    O3,
    ORG_CHART,
    SONNET,
)
from src.memory.store import memory

logger = logging.getLogger("nexus.agent")


# ---------------------------------------------------------------------------
# LLM Clients — Anthropic + OpenAI
# ---------------------------------------------------------------------------
_anthropic_client = None
_openai_client = None


from src.config import get_key as _load_key  # consolidated key loading


def get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic
        _anthropic_client = Anthropic(api_key=_load_key("ANTHROPIC_API_KEY"))
    return _anthropic_client


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=_load_key("OPENAI_API_KEY"))
    return _openai_client


def llm_call(prompt: str, model: str = HAIKU, system: str = "",
             max_tokens: int = 4096) -> tuple[str, float]:
    """Make an LLM call. Routes to Anthropic or OpenAI based on model.

    DEPRECATED: This function still returns (text, cost) tuple for backward compatibility.
    New code should use the Agent SDK bridge functions that return TaskResult.
    """
    if model == O3:
        client = get_openai_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model="o3", messages=messages, max_completion_tokens=max_tokens)
        text = response.choices[0].message.content
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
    else:
        client = get_anthropic_client()
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

    rates = MODEL_COSTS.get(model, MODEL_COSTS[SONNET])
    cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    return text, cost


async def allm_call(prompt: str, model: str = HAIKU, system: str = "",
                    max_tokens: int = 4096) -> tuple[str, float]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, llm_call, prompt, model, system, max_tokens)


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------
class Decision:
    def __init__(self, act: bool, task_id: str = "", reason: str = "",
                 action: str = "", context: dict | None = None):
        self.act = act
        self.task_id = task_id
        self.reason = reason
        self.action = action
        self.context = context or {}

    @classmethod
    def idle(cls, reason: str = "nothing to do") -> "Decision":
        return cls(act=False, reason=reason)

    @classmethod
    def from_json(cls, raw: str) -> "Decision":
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            data = json.loads(cleaned)
            return cls(act=data.get("act", False), task_id=data.get("task_id", ""),
                       reason=data.get("reason", ""), action=data.get("action", ""),
                       context=data.get("context", {}))
        except (json.JSONDecodeError, KeyError):
            return cls.idle(f"parse error: {raw[:200]}")


# ---------------------------------------------------------------------------
# Agent Base Class
# ---------------------------------------------------------------------------
class Agent(ABC):

    def __init__(self, agent_id: str):
        config = ORG_CHART.get(agent_id)
        if not config:
            raise ValueError(f"Unknown agent: {agent_id}")

        self.agent_id = agent_id
        self.name = config["name"]
        self.title = config["title"]
        self.role = config["role"]
        self.model: str = config["model"]  # type: ignore[assignment]
        self.reports_to = config["reports_to"]
        self.direct_reports: list[str] = config["direct_reports"]  # type: ignore[assignment]
        self.org = config["org"]
        self.produces = config.get("produces", [])
        self.specialty: str = config.get("specialty", "")  # type: ignore[assignment]

        self._total_cost = 0.0
        self._last_context_id = 0
        self._running = False

    def register(self):
        memory.register_agent(self.agent_id, self.name, self.title, self.model)

    @property
    def is_leader(self):
        return bool(self.direct_reports)

    @property
    def team(self):
        return self.direct_reports

    # --- Decision loop ---

    async def should_i_act(self, world_context: str) -> Decision:
        directive = memory.get_active_directive()
        if not directive:
            return Decision.idle("no active directive")

        available_tasks = memory.get_available_tasks(directive["id"])
        working_agents = memory.get_working_agents()
        board = memory.get_board_tasks(directive["id"])

        my_tasks = ""
        for t in available_tasks:
            deps_met = memory.are_dependencies_met(t["id"])
            my_tasks += f"\n  - [{t['id']}] {t['title']} (deps met: {deps_met})"

        others = ""
        for a in working_agents:
            if a["agent_id"] != self.agent_id:
                others += f"\n  - {a['name']} ({a['role']}): {a['last_action'][:60]}"

        team_status = ""
        for report_id in self.direct_reports:
            agent = memory.get_agent(report_id)
            if agent:
                team_status += f"\n  - {agent['name']}: {agent['status']} -- {agent['last_action'][:60]}"

        board_summary = ""
        if board:
            c = sum(1 for t in board if t["status"] == "complete")
            ip = sum(1 for t in board if t["status"] in ("claimed", "in_progress"))
            av = sum(1 for t in board if t["status"] == "available")
            f = sum(1 for t in board if t["status"] == "failed")
            board_summary = f"Complete: {c}, In progress: {ip}, Available: {av}, Failed: {f}"

        prompt = f"""You are {self.name}, {self.title} at Nexus.
Your role: {self.role}
You report to: {self.reports_to}
{"Your direct reports: " + ", ".join(self.direct_reports) if self.direct_reports else "You are an individual contributor."}
{"Specialty: " + self.specialty if self.specialty else ""}

CURRENT STATE:
  Directive from CEO: {directive["text"]}
  Directive status: {directive["status"]}
  Task board: {board_summary or "empty"}
  Available tasks I could claim: {my_tasks or "none"}
  Other agents working: {others or "none"}
  {"My team status: " + team_status if team_status else ""}

RECENT CONTEXT:
{world_context[-2000:]}

Should you act right now? Consider:
1. Is there work that matches your role and expertise?
2. {"As a leader, does your team need direction, unblocking, or review?" if self.is_leader else "Are there available tasks in your specialty?"}
3. Is someone else already handling it?
4. Are dependencies met for tasks you could take?

Respond ONLY with JSON:
{{"act": true/false, "task_id": "id if claiming", "reason": "why", "action": "what", "context": {{}}}}"""

        try:
            response, cost = await allm_call(prompt, HAIKU)
            self._total_cost += cost
            return Decision.from_json(response)
        except Exception as e:
            logger.error(f"[{self.name}] Decision failed: {e}")
            return Decision.idle(f"error: {e}")

    # --- Execution ---

    async def execute(self, decision: Decision, directive_id: str):
        self._running = True
        memory.update_agent(self.agent_id, status="working",
                           current_task=decision.task_id, last_action=decision.action)
        memory.emit_event(self.agent_id, "agent_started", {
            "name": self.name, "title": self.title,
            "action": decision.action, "task_id": decision.task_id})
        try:
            if decision.task_id:
                claimed = memory.claim_task(decision.task_id, self.agent_id)
                if not claimed:
                    logger.info(f"[{self.name}] Task already claimed")
                    return
                memory.start_board_task(decision.task_id)

            result = await self.do_work(decision, directive_id)

            if decision.task_id:
                memory.complete_board_task(decision.task_id, output=str(result)[:500])

            memory.post_context(self.agent_id, "work_output",
                {"agent": self.name, "title": self.title,
                 "action": decision.action, "result": str(result)[:2000]},
                directive_id=directive_id)
            memory.emit_event(self.agent_id, "agent_completed", {
                "name": self.name, "action": decision.action})

        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            if decision.task_id:
                memory.fail_board_task(decision.task_id, str(e))
            memory.post_context(self.agent_id, "error",
                {"agent": self.name, "error": str(e)}, directive_id=directive_id)
            memory.emit_event(self.agent_id, "agent_error", {
                "name": self.name, "error": str(e)[:200]})

        finally:
            self._running = False
            memory.update_agent(self.agent_id, status="idle", current_task="",
                               last_action=f"completed: {decision.action}")

    @abstractmethod
    async def do_work(self, decision: Decision, directive_id: str) -> Any:
        pass

    # --- Interruption ---

    async def check_interruption(self, directive_id: str) -> dict | None:
        interruption = memory.has_interruption(directive_id, self._last_context_id)
        if interruption:
            self._last_context_id = interruption["id"]
            logger.info(f"[{self.name}] Interruption: {interruption['content'][:100]}")
            memory.emit_event(self.agent_id, "interruption_detected", {
                "agent": self.name, "content": interruption["content"][:200]})
        return interruption  # type: ignore[no-any-return]

    def update_last_context_id(self, directive_id: str):
        latest = memory.get_latest_context(directive_id)
        if latest:
            self._last_context_id = latest["id"]

    # --- LLM helpers ---

    async def think(self, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        memory.update_agent(self.agent_id, status="thinking",
                           last_action=f"reasoning: {prompt[:50]}...")
        response, cost = await allm_call(prompt, self.model, system, max_tokens)
        self._total_cost += cost
        memory.emit_event(self.agent_id, "llm_call", {
            "agent": self.name, "model": self.model,
            "cost": round(cost, 5), "tokens_approx": len(response) // 4})
        return response

    async def think_json(self, prompt: str, system: str = "") -> dict:
        raw = await self.think(prompt + "\n\nRespond ONLY with valid JSON.", system)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        return json.loads(cleaned)  # type: ignore[no-any-return]

    # --- Hiring & Firing ---

    async def hire(self, agent_id: str, name: str, title: str, role: str,
                   model: str = SONNET, specialty: str = "") -> str:
        if not self.is_leader:
            return f"{self.name} cannot hire — not a leader."
        if agent_id in ORG_CHART:
            return f"Agent {agent_id} already exists."

        new_agent = {
            "name": name, "title": title, "role": role, "model": model,
            "reports_to": self.agent_id, "direct_reports": [], "org": self.org,
            "produces": [],
        }
        if specialty:
            new_agent["specialty"] = specialty

        ORG_CHART[agent_id] = new_agent
        ALL_AGENT_IDS.append(agent_id)
        self.direct_reports.append(agent_id)
        memory.register_agent(agent_id, name, title, model)
        memory.emit_event(self.agent_id, "agent_hired", {
            "hired_by": self.name, "new_agent": name, "title": title})
        logger.info(f"[{self.name}] Hired {name} as {title}")
        return f"Hired {name} as {title}, reporting to {self.name}"

    def fire(self, agent_id: str) -> str:
        """Only the CEO (via engine) can fire. Agents cannot fire each other."""
        return f"{self.name} cannot fire anyone. Only the CEO has that authority."

    @property
    def total_cost(self):
        return round(self._total_cost, 5)

    @property
    def is_running(self):
        return self._running

    def __repr__(self):
        return f"<{self.title} {self.name} [{self.agent_id}]>"
