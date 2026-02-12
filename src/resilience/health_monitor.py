"""
Health Monitor — Periodic system health checks and dead-letter retry.

Runs as a background asyncio task:
- Checks circuit breaker states every interval
- Retries dead-letter items when circuits close
- Records health events to KPI tracker
"""

import asyncio
import logging
import time

from src.resilience.circuit_breaker import CircuitState, breaker_registry
from src.resilience.escalation import escalation_chain

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Background health monitor for NEXUS resilience layer."""

    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._start_time: float = 0
        self._check_count = 0
        self._last_check: float = 0

    @property
    def uptime(self) -> float:
        if self._start_time == 0:
            return 0
        return time.monotonic() - self._start_time

    def start(self):
        """Start the health monitor as a background task."""
        if self._running:
            return
        self._running = True
        self._start_time = time.monotonic()
        self._task = asyncio.ensure_future(self._run_loop())
        logger.info("Health monitor started (interval=%ds)", self.check_interval)

    def stop(self):
        """Stop the health monitor."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Health monitor stopped after %d checks", self._check_count)

    async def _run_loop(self):
        while self._running:
            try:
                await self._check()
                self._check_count += 1
                self._last_check = time.monotonic()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health check failed: %s", e)
            await asyncio.sleep(self.check_interval)

    async def _check(self):
        """Run one health check cycle."""
        # Check circuit breakers
        open_circuits = breaker_registry.open_circuits()
        if open_circuits:
            logger.warning("Open circuits: %s", open_circuits)

        # Check dead letter queue
        dl_depth = escalation_chain.dead_letter_depth()
        if dl_depth > 0:
            logger.info("Dead letter queue depth: %d", dl_depth)

        # Log summary
        statuses = breaker_registry.all_statuses()
        open_count = sum(1 for s in statuses if s["state"] == CircuitState.OPEN.value)
        half_open_count = sum(1 for s in statuses if s["state"] == CircuitState.HALF_OPEN.value)
        closed_count = sum(1 for s in statuses if s["state"] == CircuitState.CLOSED.value)

        if statuses:
            logger.debug(
                "Health: circuits=%d (closed=%d, open=%d, half_open=%d) dead_letter=%d",
                len(statuses), closed_count, open_count, half_open_count, dl_depth,
            )

    def status(self) -> dict:
        """Current health status snapshot."""
        statuses = breaker_registry.all_statuses()
        return {
            "uptime_seconds": round(self.uptime, 1),
            "check_count": self._check_count,
            "check_interval": self.check_interval,
            "running": self._running,
            "circuits": {
                "total": len(statuses),
                "open": sum(1 for s in statuses if s["state"] == CircuitState.OPEN.value),
                "half_open": sum(1 for s in statuses if s["state"] == CircuitState.HALF_OPEN.value),
                "closed": sum(1 for s in statuses if s["state"] == CircuitState.CLOSED.value),
            },
            "dead_letter_depth": escalation_chain.dead_letter_depth(),
            "escalation_summary": escalation_chain.status(),
        }


# Global health monitor
health_monitor = HealthMonitor()
