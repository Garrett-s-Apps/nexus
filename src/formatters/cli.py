"""CLI/terminal-optimized response formatter."""


class CLIFormatter:
    """Formats responses for terminal output."""

    def format_response(self, text: str, agent_id: str = "", metadata: dict | None = None) -> str:
        return text  # CLI gets plain text

    def format_error(self, error: str, code: str = "") -> str:
        prefix = f"[{code}] " if code else ""
        return f"ERROR: {prefix}{error}"

    def format_status(self, directive_id: str, tasks: list[dict], cost: float = 0.0) -> str:
        lines = [f"Directive {directive_id[:8]}:"]
        for task in tasks:
            symbol = {"completed": "+", "running": "~", "failed": "!", "pending": "-"}.get(
                task.get("status", ""), "?"
            )
            lines.append(f"  [{symbol}] {task.get('description', 'Task')}")
        if cost > 0:
            lines.append(f"  Cost: ${cost:.4f}")
        return "\n".join(lines)

    def format_thinking(self, reasoning: str, agent_id: str = "") -> str:
        return f"[{agent_id}] {reasoning[:200]}"
