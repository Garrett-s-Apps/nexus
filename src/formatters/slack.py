"""Slack-optimized response formatter with threading, emoji, and rich blocks."""


class SlackFormatter:
    """Formats responses for Slack with rich formatting."""

    def format_response(self, text: str, agent_id: str = "", metadata: dict | None = None) -> str:
        return text  # Slack already gets markdown

    def format_error(self, error: str, code: str = "") -> str:
        prefix = f"`{code}` " if code else ""
        return f":warning: {prefix}{error}"

    def format_status(self, directive_id: str, tasks: list[dict], cost: float = 0.0) -> str:
        lines = [f":clipboard: *Directive Status* `{directive_id[:8]}`"]
        for task in tasks:
            status_emoji = {
                "completed": ":white_check_mark:",
                "running": ":hourglass_flowing_sand:",
                "failed": ":x:",
                "pending": ":soon:",
            }.get(task.get("status", ""), ":grey_question:")
            lines.append(f"  {status_emoji} {task.get('description', 'Task')}")
        if cost > 0:
            lines.append(f":moneybag: Cost: ${cost:.4f}")
        return "\n".join(lines)

    def format_thinking(self, reasoning: str, agent_id: str = "") -> str:
        return f":brain: _{agent_id} is thinking..._\n> {reasoning[:200]}"
