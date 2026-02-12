"""Tests for the resilience module: circuit breaker, escalation, health monitor."""

import pytest

from src.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
)
from src.resilience.escalation import EscalationChain


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test-agent")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_success_keeps_closed(self):
        cb = CircuitBreaker("test-agent")

        async def ok():
            return "ok"

        result = await cb.call(ok())
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        cb = CircuitBreaker("test-agent", failure_threshold=2)

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(self._failing_coro())

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_calls(self):
        cb = CircuitBreaker("test-agent", failure_threshold=1)

        with pytest.raises(ValueError):
            await cb.call(self._failing_coro())

        with pytest.raises(CircuitOpenError) as exc_info:
            await cb.call(self._failing_coro())
        assert "test-agent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker("test-agent", failure_threshold=1, recovery_timeout=1)

        with pytest.raises(ValueError):
            await cb.call(self._failing_coro())

        assert cb._state == CircuitState.OPEN
        cb._last_failure_time -= 2  # simulate time passing
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_success_after_half_open_closes(self):
        cb = CircuitBreaker("test-agent", failure_threshold=1, recovery_timeout=1)

        with pytest.raises(ValueError):
            await cb.call(self._failing_coro())

        cb._last_failure_time -= 2  # simulate recovery window elapsed

        async def recovered():
            return "recovered"

        result = await cb.call(recovered())
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    def test_manual_reset(self):
        cb = CircuitBreaker("test-agent", failure_threshold=1)
        cb._state = CircuitState.OPEN
        cb._failure_count = 5
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_status_dict(self):
        cb = CircuitBreaker("test-agent")
        status = cb.status()
        assert status["name"] == "test-agent"
        assert status["state"] == "closed"
        assert "failure_count" in status

    @staticmethod
    async def _failing_coro():
        raise ValueError("test failure")


class TestCircuitBreakerRegistry:
    def test_get_creates_new_breaker(self):
        reg = CircuitBreakerRegistry()
        cb = reg.get("agent-a")
        assert isinstance(cb, CircuitBreaker)
        assert cb.name == "agent-a"

    def test_get_returns_same_breaker(self):
        reg = CircuitBreakerRegistry()
        cb1 = reg.get("agent-a")
        cb2 = reg.get("agent-a")
        assert cb1 is cb2

    def test_all_statuses(self):
        reg = CircuitBreakerRegistry()
        reg.get("a")
        reg.get("b")
        statuses = reg.all_statuses()
        assert len(statuses) == 2

    def test_open_circuits_empty(self):
        reg = CircuitBreakerRegistry()
        reg.get("a")
        assert reg.open_circuits() == []

    def test_reset_all(self):
        reg = CircuitBreakerRegistry()
        cb = reg.get("a")
        cb._state = CircuitState.OPEN
        reg.reset_all()
        assert cb.state == CircuitState.CLOSED


class TestEscalationChain:
    def test_should_retry_initially_true(self):
        chain = EscalationChain(max_retries=2)
        assert chain.should_retry("agent-a") is True

    def test_retries_exhaust(self):
        chain = EscalationChain(max_retries=2)
        chain.record_retry("agent-a")
        assert chain.should_retry("agent-a") is True
        chain.record_retry("agent-a")
        assert chain.should_retry("agent-a") is False

    def test_reset_retries(self):
        chain = EscalationChain(max_retries=1)
        chain.record_retry("agent-a")
        assert chain.should_retry("agent-a") is False
        chain.reset_retries("agent-a")
        assert chain.should_retry("agent-a") is True

    def test_get_upgrade_model(self):
        chain = EscalationChain()
        assert chain.get_upgrade_model("haiku") == "sonnet"
        assert chain.get_upgrade_model("sonnet") == "opus"
        assert chain.get_upgrade_model("opus") is None

    def test_escalate_creates_event(self):
        chain = EscalationChain()
        event = chain.escalate("agent-a", "too many failures", tier=2)
        assert event.id.startswith("ESC-")
        assert event.agent == "agent-a"
        assert len(chain.recent_escalations) == 1

    def test_dead_letter(self):
        chain = EscalationChain()
        item = chain.to_dead_letter("agent-a", "build code", "timeout", 3)
        assert item.id.startswith("DL-")
        assert chain.dead_letter_depth() == 1

    def test_pop_dead_letter(self):
        chain = EscalationChain()
        item = chain.to_dead_letter("agent-a", "build code", "timeout", 3)
        popped = chain.pop_dead_letter(item.id)
        assert popped is not None
        assert chain.dead_letter_depth() == 0

    def test_pop_dead_letter_not_found(self):
        chain = EscalationChain()
        assert chain.pop_dead_letter("nonexistent") is None

    def test_status(self):
        chain = EscalationChain()
        chain.escalate("agent-a", "test")
        chain.to_dead_letter("agent-b", "op", "err", 1)
        status = chain.status()
        assert status["total_escalations"] == 1
        assert status["dead_letter_depth"] == 1
