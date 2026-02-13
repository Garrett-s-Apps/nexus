"""Neovim-optimized response formatter with compact, editor-friendly output."""


class NeovimFormatter:
    """Formats responses for Neovim integration."""

    def format_response(self, text: str, agent_id: str = "", metadata: dict | None = None) -> str:
        return text  # Neovim gets plain text

    def format_error(self, error: str, code: str = "") -> str:
        prefix = f"{code}: " if code else ""
        return f"E: {prefix}{error}"

    def format_status(self, directive_id: str, tasks: list[dict], cost: float = 0.0) -> str:
        completed = sum(1 for t in tasks if t.get("status") == "completed")
        total = len(tasks)
        return f"[{directive_id[:8]}] {completed}/{total} tasks"

    def format_thinking(self, reasoning: str, agent_id: str = "") -> str:
        return f"-- {agent_id}: {reasoning[:100]}"
