"""Action routing — maps classified intents to handler functions."""

import logging
from collections.abc import Callable
from typing import Any

from src.agents.intent_classifier import IntentResult, IntentType

logger = logging.getLogger("nexus.action_router")


class ActionRouter:
    """Routes classified intents to appropriate handlers.

    Does not know how to classify (that's IntentClassifier's job).
    Does not know how to execute (that's the handler's job).
    Only knows which handler to call for which intent.
    """

    def __init__(self) -> None:
        self._handlers: dict[IntentType, Callable] = {}

    def register(self, intent_type: IntentType, handler: Callable) -> None:
        """Register a handler for an intent type."""
        self._handlers[intent_type] = handler
        logger.debug("Registered handler for %s", intent_type.value)

    async def route(self, intent: IntentResult, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Route an intent to its handler.

        Args:
            intent: The classified intent result
            context: Optional context dict to pass to the handler

        Returns:
            Handler response dict, or error dict if no handler registered
        """
        handler = self._handlers.get(intent.intent)
        if not handler:
            logger.warning("No handler registered for %s", intent.intent.value)
            return {"error": f"No handler for {intent.intent.value}"}

        logger.info(
            "Routing %s (confidence=%.2f) to %s",
            intent.intent.value,
            intent.confidence,
            handler.__name__,
        )
        result: dict[str, Any] = await handler(intent, context or {})
        return result


action_router = ActionRouter()
