"""Tests for NEXUS ReasoningEngine — message handling, decomposition, and NLU."""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


@pytest.fixture
def mock_memory():
    """Mock the memory singleton used by the engine."""
    mem = MagicMock()
    mem.add_message = MagicMock()
    mem.get_active_directive = MagicMock(return_value=None)
    mem.create_directive = MagicMock(return_value={"id": "dir-test", "text": "test", "status": "received"})
    mem.post_context = MagicMock()
    mem.update_directive = MagicMock()
    mem.get_board_tasks = MagicMock(return_value=[])
    mem.get_open_defects = MagicMock(return_value=[])
    mem.get_working_agents = MagicMock(return_value=[])
    mem.emit_event = MagicMock()
    mem.get_latest_event_id = MagicMock(return_value=0)
    mem.get_events_since = MagicMock(return_value=[])
    mem.get_available_tasks = MagicMock(return_value=[])
    mem.create_board_task = MagicMock()
    mem.get_context_for_directive = MagicMock(return_value=[])
    return mem


@pytest.fixture
def engine_with_mocks(mock_memory):
    """Create a ReasoningEngine with all external deps mocked."""
    with patch("src.orchestrator.engine.memory", mock_memory), \
         patch("src.orchestrator.engine.notify_slack", new_callable=AsyncMock), \
         patch("src.orchestrator.engine.allm_call", new_callable=AsyncMock) as mock_llm, \
         patch("src.orchestrator.engine.create_all_agents", return_value={}):
        mock_llm.return_value = ('{"intent": "chat", "summary": "test", "response": "Hello!"}', 0.001)
        from src.orchestrator.engine import ReasoningEngine
        eng = ReasoningEngine()
        yield eng, mock_memory, mock_llm


class TestEngineStartStop:
    @pytest.mark.asyncio
    async def test_engine_start_stop(self, engine_with_mocks):
        """Engine should start and stop cleanly."""
        eng, mock_mem, _ = engine_with_mocks
        await eng.start()
        assert eng.running is True
        assert eng._task is not None

        await eng.stop()
        assert eng.running is False


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_handle_message_chat(self, engine_with_mocks):
        """Chat intent should return the LLM's response."""
        eng, mock_mem, mock_llm = engine_with_mocks
        mock_llm.return_value = ('{"intent": "chat", "summary": "hello", "response": "Hey there!"}', 0.001)

        response = await eng.handle_message("hello", source="slack")
        assert response == "Hey there!"
        assert mock_mem.add_message.call_count == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_handle_message_new_directive(self, engine_with_mocks):
        """New directive intent should create a directive and return confirmation."""
        eng, mock_mem, mock_llm = engine_with_mocks
        mock_llm.return_value = ('{"intent": "new_directive", "summary": "build app", "response": "Starting!", "urgency": "normal", "target": ""}', 0.001)

        response = await eng.handle_message("Build me an app", source="slack")
        assert "dir-" in response.lower() or "directive" in response.lower() or "created" in response.lower()
        mock_mem.create_directive.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_status(self, engine_with_mocks):
        """Status intent with no active directive should return standing by."""
        eng, mock_mem, mock_llm = engine_with_mocks
        mock_llm.return_value = ('{"intent": "status", "summary": "check status", "response": ""}', 0.001)

        response = await eng.handle_message("What's the status?", source="slack")
        assert "standing by" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_message_stop(self, engine_with_mocks):
        """Stop intent with no active directive should indicate nothing to stop."""
        eng, mock_mem, mock_llm = engine_with_mocks
        mock_llm.return_value = ('{"intent": "stop", "summary": "stop", "response": ""}', 0.001)

        response = await eng.handle_message("Stop everything", source="slack")
        assert "nothing" in response.lower() or "active" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_message_feedback_no_directive(self, engine_with_mocks):
        """Feedback with no active directive should say there's nothing active."""
        eng, mock_mem, mock_llm = engine_with_mocks
        mock_llm.return_value = ('{"intent": "feedback", "summary": "change the color", "response": ""}', 0.001)

        response = await eng.handle_message("Change the button color", source="slack")
        assert "no active" in response.lower() or "nothing" in response.lower()


class TestFastDecompose:
    @pytest.mark.asyncio
    async def test_fast_decompose(self, mock_memory):
        """fast_decompose should create tasks from LLM output."""
        tasks_json = json.dumps([
            {"id": "task-1", "title": "Create model", "description": "DB model", "priority": 10, "depends_on": []},
            {"id": "task-2", "title": "Create API", "description": "REST API", "priority": 8, "depends_on": ["task-1"]},
        ])

        with patch("src.orchestrator.engine.memory", mock_memory), \
             patch("src.orchestrator.engine.allm_call", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (tasks_json, 0.01)

            from src.orchestrator.engine import fast_decompose
            count = await fast_decompose("Build user auth", "dir-test")

            assert count == 2
            assert mock_memory.create_board_task.call_count == 2

    @pytest.mark.asyncio
    async def test_fast_decompose_empty_response(self, mock_memory):
        """fast_decompose should handle empty/invalid LLM responses gracefully."""
        with patch("src.orchestrator.engine.memory", mock_memory), \
             patch("src.orchestrator.engine.allm_call", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ("not valid json at all", 0.01)

            # Need to also mock extract_json to return None for bad JSON
            with patch("src.orchestrator.engine.extract_json", return_value=None):
                from src.orchestrator.engine import fast_decompose
                count = await fast_decompose("Do something vague", "dir-empty")
                assert count == 0


class TestUnderstandIntent:
    @pytest.mark.asyncio
    async def test_understand_intent_classification(self, mock_memory):
        """understand() should classify messages into intents."""
        with patch("src.orchestrator.engine.memory", mock_memory), \
             patch("src.orchestrator.engine.allm_call", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ('{"intent": "new_directive", "summary": "build", "urgency": "normal", "target": "", "response": ""}', 0.001)

            from src.orchestrator.engine import understand
            result = await understand("Build me a new website")

            assert result["intent"] == "new_directive"
            assert "summary" in result

    @pytest.mark.asyncio
    async def test_understand_fallback_on_bad_json(self, mock_memory):
        """understand() should fallback to chat intent on invalid JSON."""
        with patch("src.orchestrator.engine.memory", mock_memory), \
             patch("src.orchestrator.engine.allm_call", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ("this is not json", 0.001)

            from src.orchestrator.engine import understand
            result = await understand("Something weird")

            assert result["intent"] == "chat"


class TestSafeRun:
    @pytest.mark.asyncio
    async def test_safe_run_error_handling(self, engine_with_mocks):
        """_safe_run should catch exceptions and log them without crashing."""
        eng, mock_mem, _ = engine_with_mocks

        mock_agent = MagicMock()
        mock_agent.name = "TestAgent"
        mock_agent.execute = AsyncMock(side_effect=RuntimeError("Agent crashed"))
        eng.agents["test_agent"] = mock_agent

        from src.orchestrator.engine import Decision
        decision = Decision(act=True, action="Do work")

        # Should not raise
        await eng._safe_run("test_agent", decision, "dir-test")
        mock_mem.emit_event.assert_called()

    @pytest.mark.asyncio
    async def test_safe_run_nonexistent_agent(self, engine_with_mocks):
        """_safe_run with a nonexistent agent should do nothing."""
        eng, mock_mem, _ = engine_with_mocks
        from src.orchestrator.engine import Decision
        decision = Decision(act=True, action="Do work")

        # Should not raise for missing agent
        await eng._safe_run("nonexistent", decision, "dir-test")
