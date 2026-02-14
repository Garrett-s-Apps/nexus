"""Tests for NEXUS Memory store — CRUD operations on all world-state tables."""



class TestMemoryInit:
    def test_init_creates_tables(self, memory_db):
        """Memory.init() should create all required tables."""
        cursor = memory_db._conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            "messages", "summaries", "projects", "project_notes", "context",
            "tasks", "directives", "world_context", "task_board", "agent_state",
            "event_log", "running_services", "defects", "peer_decisions",
        }
        assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"


class TestMessages:
    def test_add_and_get_messages(self, memory_db):
        """Adding messages should be retrievable in chronological order."""
        memory_db.add_message("user", "Hello NEXUS")
        memory_db.add_message("assistant", "Hello Garrett")
        memory_db.add_message("user", "Build me an app")

        msgs = memory_db.get_recent_messages(limit=10)
        assert len(msgs) == 3
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello NEXUS"
        assert msgs[1]["role"] == "assistant"
        assert msgs[2]["content"] == "Build me an app"

    def test_message_count(self, memory_db):
        """get_message_count should reflect the number of stored messages."""
        assert memory_db.get_message_count() == 0
        memory_db.add_message("user", "First")
        memory_db.add_message("user", "Second")
        assert memory_db.get_message_count() == 2


class TestDirectives:
    def test_create_and_get_directive(self, memory_db):
        """Creating a directive should persist and be retrievable."""
        result = memory_db.create_directive("dir-001", "Build an API", intent="new_directive", project_path="/tmp/proj")
        assert result["id"] == "dir-001"
        assert result["status"] == "received"

        d = memory_db.get_directive("dir-001")
        assert d is not None
        assert d["text"] == "Build an API"
        assert d["intent"] == "new_directive"
        assert d["project_path"] == "/tmp/proj"

    def test_get_active_directive(self, memory_db):
        """get_active_directive should return the most recent non-complete directive."""
        memory_db.create_directive("dir-old", "Old directive")
        memory_db.update_directive("dir-old", status="complete")
        memory_db.create_directive("dir-active", "Active directive")

        active = memory_db.get_active_directive()
        assert active is not None
        assert active["id"] == "dir-active"

    def test_update_directive_status(self, memory_db):
        """update_directive should change status and update timestamp."""
        memory_db.create_directive("dir-upd", "Test update")
        memory_db.update_directive("dir-upd", status="building")

        d = memory_db.get_directive("dir-upd")
        assert d["status"] == "building"


class TestTaskBoard:
    def test_create_and_get_board_tasks(self, memory_db):
        """Creating board tasks should be retrievable by directive_id."""
        memory_db.create_directive("dir-t", "Task test")
        memory_db.create_board_task("t-1", "dir-t", "Build UI", priority=10)
        memory_db.create_board_task("t-2", "dir-t", "Build API", priority=5)

        tasks = memory_db.get_board_tasks("dir-t")
        assert len(tasks) == 2
        # Sorted by priority DESC
        assert tasks[0]["title"] == "Build UI"
        assert tasks[1]["title"] == "Build API"

    def test_claim_and_complete_task(self, memory_db):
        """Claiming and completing tasks should update status correctly."""
        memory_db.create_directive("dir-c", "Claim test")
        memory_db.create_board_task("t-c1", "dir-c", "Task to claim")

        ok = memory_db.claim_task("t-c1", "fe_engineer_1")
        assert ok is True

        # Task is now claimed; available list should be empty
        available = memory_db.get_available_tasks("dir-c")
        assert len(available) == 0

        memory_db.complete_board_task("t-c1", output="Done")
        tasks = memory_db.get_board_tasks("dir-c")
        assert tasks[0]["status"] == "complete"
        assert tasks[0]["output"] == "Done"

    def test_claim_already_claimed_task_fails(self, memory_db):
        """Claiming an already-claimed task should fail (return False)."""
        memory_db.create_directive("dir-cc", "Double claim")
        memory_db.create_board_task("t-cc", "dir-cc", "Contested task")

        assert memory_db.claim_task("t-cc", "eng1") is True
        assert memory_db.claim_task("t-cc", "eng2") is False

    def test_dependencies_met(self, memory_db):
        """are_dependencies_met should check that all dependencies are complete."""
        memory_db.create_directive("dir-dep", "Deps test")
        memory_db.create_board_task("dep-1", "dir-dep", "Foundation", depends_on=[])
        memory_db.create_board_task("dep-2", "dir-dep", "Depends on foundation", depends_on=["dep-1"])

        # dep-2 depends on dep-1 which is not complete yet
        assert memory_db.are_dependencies_met("dep-2") is False

        # Complete dep-1
        memory_db.complete_board_task("dep-1")
        assert memory_db.are_dependencies_met("dep-2") is True

    def test_dependencies_met_no_deps(self, memory_db):
        """A task with no dependencies should always have dependencies met."""
        memory_db.create_directive("dir-nodep", "No deps")
        memory_db.create_board_task("nd-1", "dir-nodep", "Standalone task", depends_on=[])
        assert memory_db.are_dependencies_met("nd-1") is True

    def test_fail_and_reset_task(self, memory_db):
        """Failing a task should set status to failed; reset should make it available."""
        memory_db.create_directive("dir-fr", "Fail reset")
        memory_db.create_board_task("fr-1", "dir-fr", "Task to fail")

        memory_db.claim_task("fr-1", "eng1")
        memory_db.fail_board_task("fr-1", error="Compilation error")
        task = memory_db.get_board_tasks("dir-fr")[0]
        assert task["status"] == "failed"
        assert "Compilation error" in task["output"]

        memory_db.reset_board_task("fr-1")
        task = memory_db.get_board_tasks("dir-fr")[0]
        assert task["status"] == "available"


class TestAgentState:
    def test_register_and_get_agents(self, memory_db):
        """Registering agents should persist and be queryable."""
        memory_db.register_agent("eng1", "Derek", "frontend_engineer", model="sonnet")
        memory_db.register_agent("eng2", "Caleb", "backend_engineer", model="sonnet")

        agents = memory_db.get_all_agents()
        assert len(agents) == 2
        assert agents[0]["name"] == "Caleb" or agents[1]["name"] == "Caleb"

        agent = memory_db.get_agent("eng1")
        assert agent["name"] == "Derek"
        assert agent["status"] == "idle"

    def test_update_agent_status(self, memory_db):
        """Updating agent status should reflect in queries."""
        memory_db.register_agent("eng_w", "Nathan", "engineer")
        memory_db.update_agent("eng_w", status="working", last_action="Building UI")

        agent = memory_db.get_agent("eng_w")
        assert agent["status"] == "working"
        assert agent["last_action"] == "Building UI"

        working = memory_db.get_working_agents()
        assert len(working) == 1
        assert working[0]["agent_id"] == "eng_w"

    def test_idle_agents(self, memory_db):
        """get_idle_agents should return only agents with idle status."""
        memory_db.register_agent("idle1", "A", "role1")
        memory_db.register_agent("busy1", "B", "role2")
        memory_db.update_agent("busy1", status="working")

        idle = memory_db.get_idle_agents()
        assert len(idle) == 1
        assert idle[0]["agent_id"] == "idle1"


class TestEvents:
    def test_emit_and_get_events(self, memory_db):
        """Emitting events should be queryable by id."""
        memory_db.emit_event("system", "directive_created", {"id": "dir-1"})
        memory_db.emit_event("eng1", "task_claimed", {"task_id": "t-1"})

        events = memory_db.get_recent_events(limit=10)
        assert len(events) == 2
        assert events[0]["event_type"] == "directive_created"
        assert events[1]["event_type"] == "task_claimed"

    def test_events_since(self, memory_db):
        """get_events_since should filter events after a given id."""
        memory_db.emit_event("a", "type1", {})
        memory_db.emit_event("b", "type2", {})
        memory_db.emit_event("c", "type3", {})

        all_events = memory_db.get_recent_events(limit=10)
        first_id = all_events[0]["id"]

        since = memory_db.get_events_since(first_id, limit=10)
        assert len(since) == 2  # only events after the first

    def test_latest_event_id(self, memory_db):
        """get_latest_event_id should return the highest event id."""
        assert memory_db.get_latest_event_id() == 0
        memory_db.emit_event("sys", "test", {})
        assert memory_db.get_latest_event_id() > 0


class TestDefects:
    def test_create_and_resolve_defects(self, memory_db):
        """Creating and resolving defects should update status correctly."""
        memory_db.create_directive("dir-def", "Defect test")
        memory_db.create_defect(
            "bug-1", "dir-def", "t-1",
            title="Null pointer", description="Crashes on empty input",
            severity="HIGH", filed_by="qa_lead"
        )

        defects = memory_db.get_open_defects("dir-def")
        assert len(defects) == 1
        assert defects[0]["title"] == "Null pointer"
        assert defects[0]["severity"] == "HIGH"

        memory_db.resolve_defect("bug-1", resolved_by="eng1")
        defects = memory_db.get_open_defects("dir-def")
        assert len(defects) == 0

    def test_assign_defect(self, memory_db):
        """Assigning a defect should update assigned_to."""
        memory_db.create_directive("dir-asgn", "Assign test")
        memory_db.create_defect("bug-a", "dir-asgn", "t-a", "Bug A", "desc", filed_by="qa")

        memory_db.assign_defect("bug-a", "fe_engineer_1")
        defects = memory_db.get_open_defects("dir-asgn")
        assert defects[0]["assigned_to"] == "fe_engineer_1"

    def test_defects_for_task(self, memory_db):
        """get_defects_for_task should filter by task_id."""
        memory_db.create_directive("dir-dft", "Task defects")
        memory_db.create_defect("bug-t1", "dir-dft", "task-a", "Bug in A", "desc", filed_by="qa")
        memory_db.create_defect("bug-t2", "dir-dft", "task-b", "Bug in B", "desc", filed_by="qa")

        a_defects = memory_db.get_defects_for_task("task-a")
        assert len(a_defects) == 1
        assert a_defects[0]["id"] == "bug-t1"


class TestWorldSnapshot:
    def test_world_snapshot(self, memory_db):
        """get_world_snapshot should assemble a coherent snapshot of the world state."""
        memory_db.create_directive("dir-snap", "Snapshot test")
        memory_db.create_board_task("snap-t1", "dir-snap", "Build something")
        memory_db.register_agent("snap-eng", "Test Eng", "engineer")

        snapshot = memory_db.get_world_snapshot()
        assert snapshot["directive"] is not None
        assert snapshot["directive"]["id"] == "dir-snap"
        assert len(snapshot["task_board"]) == 1
        assert len(snapshot["agents"]) == 1
        assert "stats" in snapshot
        assert snapshot["stats"]["total_messages"] == 0
