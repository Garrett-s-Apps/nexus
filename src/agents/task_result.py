"""
Anti-Corruption Layer — canonical result type for all provider integrations.

Every provider (Claude Code CLI, Agent SDK, Gemini, o3, direct Anthropic API)
returns a TaskResult. Consumers never depend on provider-specific shapes.
"""

from dataclasses import dataclass, field


@dataclass
class TaskResult:
    status: str  # "success", "error", "timeout", "unavailable"
    output: str
    error_type: str = ""  # "timeout", "cli_not_found", "api_error", "circuit_open"
    error_detail: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    model: str = ""
    agent: str = ""
    elapsed_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict:
        return {
            "output": self.output,
            "status": self.status,
            "error_type": self.error_type,
            "error_detail": self.error_detail,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost": self.cost_usd,
            "model": self.model,
            "agent": self.agent,
            "elapsed_seconds": self.elapsed_seconds,
        }
