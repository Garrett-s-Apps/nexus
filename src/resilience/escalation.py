"""
Escalation Chain — Tiered failure recovery.

1. First failure → retry with same agent (up to max_retries)
2. Retries exhausted → circuit opens → escalate to higher-tier agent
3. Higher-tier failure → file defect + notify CEO in Slack thread
4. Dead letter → store failed operation for manual review / batch retry
"""

import logging
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EscalationEvent:
    id: str
    agent: str
    reason: str
    tier: int
    outcome: str = "pending"
    defect_id: str | None = None


@dataclass
class DeadLetterItem:
    id: str
    agent: str
    operation: str
    error: str
    attempts: int
    created_at: float = 0.0


class EscalationChain:
    """Manages tiered escalation from retry → upgrade → CEO notification → dead letter."""

    # Agent tier mapping: higher tier = more capable
    TIER_MAP = {
        "haiku": 1,
        "sonnet": 2,
        "opus": 3,
    }

    TIER_UPGRADE = {
        1: "sonnet",
        2: "opus",
        3: None,  # top tier, escalate to CEO
    }

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self._events: list[EscalationEvent] = []
        self._dead_letter: list[DeadLetterItem] = []
        self._retry_counts: dict[str, int] = {}

    def should_retry(self, agent: str) -> bool:
        """Check if the agent still has retries available."""
        count = self._retry_counts.get(agent, 0)
        return count < self.max_retries

    def record_retry(self, agent: str) -> int:
        """Record a retry attempt. Returns current retry count."""
        self._retry_counts[agent] = self._retry_counts.get(agent, 0) + 1
        count = self._retry_counts[agent]
        logger.info("Retry %d/%d for agent '%s'", count, self.max_retries, agent)
        return count

    def reset_retries(self, agent: str):
        """Reset retry count on success."""
        self._retry_counts.pop(agent, None)

    def get_upgrade_model(self, current_model_tier: str) -> str | None:
        """Get the next tier model for escalation. Returns None if at top tier."""
        tier = self.TIER_MAP.get(current_model_tier, 2)
        return self.TIER_UPGRADE.get(tier)

    def escalate(self, agent: str, reason: str, tier: int = 1) -> EscalationEvent:
        """Record an escalation event."""
        event = EscalationEvent(
            id=f"ESC-{uuid.uuid4().hex[:8]}",
            agent=agent,
            reason=reason,
            tier=tier,
        )
        self._events.append(event)
        logger.warning("Escalation [%s] tier=%d agent=%s: %s", event.id, tier, agent, reason)
        return event

    def to_dead_letter(self, agent: str, operation: str, error: str, attempts: int) -> DeadLetterItem:
        """Move a failed operation to the dead letter queue."""
        item = DeadLetterItem(
            id=f"DL-{uuid.uuid4().hex[:8]}",
            agent=agent,
            operation=operation[:500],
            error=error[:500],
            attempts=attempts,
        )
        self._dead_letter.append(item)
        logger.error("Dead letter [%s] agent=%s after %d attempts: %s", item.id, agent, attempts, error[:200])
        return item

    @property
    def dead_letter_queue(self) -> list[DeadLetterItem]:
        return list(self._dead_letter)

    @property
    def recent_escalations(self) -> list[EscalationEvent]:
        return list(self._events[-20:])

    def dead_letter_depth(self) -> int:
        return len(self._dead_letter)

    def pop_dead_letter(self, item_id: str) -> DeadLetterItem | None:
        """Remove and return a dead letter item for retry."""
        for i, item in enumerate(self._dead_letter):
            if item.id == item_id:
                return self._dead_letter.pop(i)
        return None

    def status(self) -> dict:
        return {
            "total_escalations": len(self._events),
            "dead_letter_depth": len(self._dead_letter),
            "active_retries": {k: v for k, v in self._retry_counts.items() if v > 0},
            "recent_escalations": [
                {"id": e.id, "agent": e.agent, "reason": e.reason[:100], "tier": e.tier}
                for e in self._events[-5:]
            ],
        }


# Global escalation chain
escalation_chain = EscalationChain()
