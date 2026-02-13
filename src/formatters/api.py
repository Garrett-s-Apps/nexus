"""Structured JSON API response formatter."""

import json


class APIFormatter:
    """Formats responses as structured JSON for programmatic consumers."""

    def format_response(self, text: str, agent_id: str = "", metadata: dict | None = None) -> str:
        result: dict = {"text": text, "agent": agent_id}
        if metadata:
            result["metadata"] = metadata
        return json.dumps(result)

    def format_error(self, error: str, code: str = "") -> str:
        result = {"error": error}
        if code:
            result["code"] = code
        return json.dumps(result)

    def format_status(self, directive_id: str, tasks: list[dict], cost: float = 0.0) -> str:
        return json.dumps({
            "directive_id": directive_id,
            "tasks": tasks,
            "cost_usd": cost,
        })

    def format_thinking(self, reasoning: str, agent_id: str = "") -> str:
        return json.dumps({"type": "thinking", "agent": agent_id, "reasoning": reasoning})
