"""
Circuit Breaker — Per-agent failure isolation.

States: CLOSED (normal) → OPEN (failing, reject calls) → HALF_OPEN (test one call)

When an agent fails repeatedly, the circuit opens to prevent cascade failures.
After a recovery timeout, one test call is allowed through (half-open).
If it succeeds, circuit closes. If it fails, circuit re-opens.
"""

import asyncio
import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, name: str, time_until_retry: float):
        self.name = name
        self.time_until_retry = time_until_retry
        super().__init__(f"Circuit '{name}' is OPEN. Retry in {time_until_retry:.0f}s")


class CircuitBreaker:
    """Per-agent circuit breaker with configurable thresholds."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._success_count = 0
        self._total_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self._total_calls,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }

    async def call(self, coro):
        """Execute a coroutine through the circuit breaker."""
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                time_left = self.recovery_timeout - (time.monotonic() - self._last_failure_time)
                raise CircuitOpenError(self.name, max(0, time_left))

        self._total_calls += 1

        try:
            result = await coro
            await self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as e:
            await self._on_failure(e)
            raise

    async def _on_success(self):
        async with self._lock:
            self._failure_count = 0
            self._success_count += 1
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info("Circuit '%s' recovered → CLOSED", self.name)
            self._state = CircuitState.CLOSED

    async def _on_failure(self, error: Exception):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        "Circuit '%s' tripped → OPEN after %d failures: %s",
                        self.name, self._failure_count, error,
                    )
                self._state = CircuitState.OPEN

    def reset(self):
        """Manually reset the circuit to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        logger.info("Circuit '%s' manually reset → CLOSED", self.name)


class CircuitBreakerRegistry:
    """Manages circuit breakers for all agents."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._default_failure_threshold = failure_threshold
        self._default_recovery_timeout = recovery_timeout

    def get(self, agent_name: str) -> CircuitBreaker:
        if agent_name not in self._breakers:
            self._breakers[agent_name] = CircuitBreaker(
                name=agent_name,
                failure_threshold=self._default_failure_threshold,
                recovery_timeout=self._default_recovery_timeout,
            )
        return self._breakers[agent_name]

    def all_statuses(self) -> list[dict]:
        return [cb.status() for cb in self._breakers.values()]

    def open_circuits(self) -> list[str]:
        return [
            name for name, cb in self._breakers.items()
            if cb.state == CircuitState.OPEN
        ]

    def reset_all(self):
        for cb in self._breakers.values():
            cb.reset()


# Global registry
breaker_registry = CircuitBreakerRegistry()
