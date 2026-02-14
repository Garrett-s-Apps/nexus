"""Tests for NEXUS SessionStore — async SQLite session persistence."""


import pytest

from src.session.store import SessionStore


@pytest.fixture
async def session_store(tmp_path):
    """Fresh session store with temp database."""
    db_path = str(tmp_path / "test_sessions.db")
    store = SessionStore(db_path=db_path)
    await store.init()
    return store


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session(self, session_store):
        """Creating a session should return session data with correct fields."""
        session = await session_store.create_session(
            session_id="sess-001",
            directive="Build an API",
            source="slack",
            project_path="/tmp/my-project",
        )
        assert session["id"] == "sess-001"
        assert session["directive"] == "Build an API"
        assert session["source"] == "slack"
        assert session["status"] == "running"
        assert "created_at" in session

    @pytest.mark.asyncio
    async def test_create_session_defaults(self, session_store):
        """Creating a session with minimal args should use defaults."""
        session = await session_store.create_session(
            session_id="sess-min",
            directive="Test directive",
        )
        assert session["source"] == "slack"
        assert session["status"] == "running"


class TestGetSession:
    @pytest.mark.asyncio
    async def test_get_session(self, session_store):
        """Getting a session should return full session data with messages."""
        await session_store.create_session("sess-get", "Test get")
        session = await session_store.get_session("sess-get")

        assert session is not None
        assert session["id"] == "sess-get"
        assert session["directive"] == "Test get"
        assert "messages" in session

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, session_store):
        """Getting a nonexistent session should return None."""
        session = await session_store.get_session("nonexistent-id")
        assert session is None

    @pytest.mark.asyncio
    async def test_get_session_with_state(self, session_store):
        """Session with saved state should include state in the response."""
        await session_store.create_session("sess-state", "State test")
        await session_store.save_state("sess-state", {"phase": "building", "progress": 50})

        session = await session_store.get_session("sess-state")
        assert "state" in session
        assert session["state"]["phase"] == "building"


class TestListSessions:
    @pytest.mark.asyncio
    async def test_list_sessions(self, session_store):
        """Listing sessions should return all created sessions."""
        await session_store.create_session("sess-a", "Directive A")
        await session_store.create_session("sess-b", "Directive B")

        sessions = await session_store.get_recent_sessions(limit=10)
        assert len(sessions) == 2

    @pytest.mark.asyncio
    async def test_list_sessions_respects_limit(self, session_store):
        """Session listing should respect the limit parameter."""
        for i in range(5):
            await session_store.create_session(f"sess-lim-{i}", f"Directive {i}")

        sessions = await session_store.get_recent_sessions(limit=3)
        assert len(sessions) == 3

    @pytest.mark.asyncio
    async def test_list_sessions_ordered_by_created(self, session_store):
        """Sessions should be ordered by creation time descending."""
        await session_store.create_session("sess-first", "First")
        await session_store.create_session("sess-second", "Second")

        sessions = await session_store.get_recent_sessions(limit=10)
        # Most recent first
        assert sessions[0]["id"] == "sess-second"


class TestSessionMessages:
    @pytest.mark.asyncio
    async def test_add_message_to_session(self, session_store):
        """Adding messages to a session should be persisted."""
        await session_store.create_session("sess-msg", "Message test")
        await session_store.add_message("sess-msg", "user", "Hello", agent=None, cost=0.0)
        await session_store.add_message("sess-msg", "assistant", "Hi there", agent="eng1", cost=0.01)

        session = await session_store.get_session("sess-msg")
        assert len(session["messages"]) == 2
        assert session["messages"][0]["role"] == "user"
        assert session["messages"][1]["role"] == "assistant"
        assert session["messages"][1]["agent"] == "eng1"

    @pytest.mark.asyncio
    async def test_get_session_messages(self, session_store):
        """get_session_messages should return messages in order."""
        await session_store.create_session("sess-msgs", "Messages test")
        await session_store.add_message("sess-msgs", "user", "First")
        await session_store.add_message("sess-msgs", "assistant", "Second")
        await session_store.add_message("sess-msgs", "user", "Third")

        messages = await session_store.get_session_messages("sess-msgs")
        assert len(messages) == 3
        assert messages[0]["content"] == "First"
        assert messages[2]["content"] == "Third"

    @pytest.mark.asyncio
    async def test_message_cost_updates_session(self, session_store):
        """Adding a message with cost should update the session's total_cost."""
        await session_store.create_session("sess-cost", "Cost test")
        await session_store.add_message("sess-cost", "assistant", "Response", cost=0.05)
        await session_store.add_message("sess-cost", "assistant", "Another", cost=0.10)

        session = await session_store.get_session("sess-cost")
        assert session["total_cost"] >= 0.15


class TestSessionStatus:
    @pytest.mark.asyncio
    async def test_update_status(self, session_store):
        """Updating session status should persist the change."""
        await session_store.create_session("sess-status", "Status test")
        await session_store.update_status("sess-status", "complete")

        session = await session_store.get_session("sess-status")
        assert session["status"] == "complete"
        assert session["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_status_with_error(self, session_store):
        """Updating status with an error should store the error."""
        await session_store.create_session("sess-err", "Error test")
        await session_store.update_status("sess-err", "failed", error="Something broke")

        session = await session_store.get_session("sess-err")
        assert session["status"] == "failed"
        assert session["error"] == "Something broke"


class TestTotalCost:
    @pytest.mark.asyncio
    async def test_total_cost(self, session_store):
        """get_total_cost should sum costs across all sessions."""
        await session_store.create_session("sess-tc1", "Cost 1")
        await session_store.add_message("sess-tc1", "assistant", "R1", cost=1.0)
        await session_store.create_session("sess-tc2", "Cost 2")
        await session_store.add_message("sess-tc2", "assistant", "R2", cost=2.0)

        total = await session_store.get_total_cost()
        assert total >= 3.0
