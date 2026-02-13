"""Response formatter protocol for BFF pattern."""

from typing import Protocol


class ResponseFormatter(Protocol):
    """Protocol for formatting responses per client type."""

    def format_response(self, text: str, agent_id: str = "", metadata: dict | None = None) -> str:
        """Format the main response text."""
        ...

    def format_error(self, error: str, code: str = "") -> str:
        """Format error messages."""
        ...

    def format_status(self, directive_id: str, tasks: list[dict], cost: float = 0.0) -> str:
        """Format directive status updates."""
        ...

    def format_thinking(self, reasoning: str, agent_id: str = "") -> str:
        """Format orchestrator thinking/reasoning."""
        ...
