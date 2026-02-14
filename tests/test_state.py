"""Tests for NEXUS State models — NexusState, WorkstreamTask, PRReview, CostSnapshot."""

from src.orchestrator.state import CostSnapshot, NexusState, PRReview, WorkstreamTask


class TestNexusState:
    def test_nexus_state_defaults(self):
        """NexusState should initialize with sensible defaults."""
        state = NexusState()
        assert state.directive == ""
        assert state.source == "slack"
        assert state.current_phase == "intake"
        assert state.ceo_approved is False
        assert state.executive_consensus is False
        assert state.workstreams == []
        assert state.files_changed == []
        assert state.pr_approved is False
        assert state.error is None

    def test_nexus_state_with_values(self):
        """NexusState should accept and store provided values."""
        state = NexusState(
            directive="Build a REST API",
            source="cli",
            session_id="sess-001",
            project_path="/tmp/my-project",
            current_phase="implementation",
            ceo_approved=True,
        )
        assert state.directive == "Build a REST API"
        assert state.source == "cli"
        assert state.session_id == "sess-001"
        assert state.project_path == "/tmp/my-project"
        assert state.current_phase == "implementation"
        assert state.ceo_approved is True

    def test_nexus_state_cost_snapshot_embedded(self):
        """NexusState should embed a default CostSnapshot."""
        state = NexusState()
        assert isinstance(state.cost, CostSnapshot)
        assert state.cost.total_cost_usd == 0.0

    def test_nexus_state_all_phases_valid(self):
        """All defined phases should be assignable."""
        phases = [
            "intake", "executive_planning", "technical_planning",
            "decomposition", "implementation", "quality_gate",
            "pr_review", "demo", "complete", "escalation",
        ]
        for phase in phases:
            state = NexusState(current_phase=phase)
            assert state.current_phase == phase

    def test_nexus_state_list_fields_are_mutable(self):
        """List fields should be independent across instances."""
        s1 = NexusState()
        s2 = NexusState()
        s1.workstreams.append(WorkstreamTask(id="t1", description="test", assigned_agent="eng1"))
        assert len(s2.workstreams) == 0


class TestWorkstreamTask:
    def test_workstream_task_creation(self):
        """WorkstreamTask should create with required and default fields."""
        task = WorkstreamTask(
            id="ws-1",
            description="Build user model",
            assigned_agent="be_engineer_1",
        )
        assert task.id == "ws-1"
        assert task.status == "pending"
        assert task.files == []
        assert task.token_cost == 0.0
        assert task.attempts == 0
        assert task.language is None
        assert task.result is None

    def test_workstream_task_with_all_fields(self):
        """WorkstreamTask should accept all optional fields."""
        task = WorkstreamTask(
            id="ws-2",
            description="Build API endpoint",
            assigned_agent="be_engineer_1",
            language="python",
            files=["src/api.py", "src/models.py"],
            status="in_progress",
            result="Created 2 files",
            token_cost=0.05,
            attempts=2,
        )
        assert task.language == "python"
        assert len(task.files) == 2
        assert task.status == "in_progress"
        assert task.attempts == 2

    def test_workstream_task_status_values(self):
        """All valid status values should be assignable."""
        for status in ["pending", "in_progress", "completed", "failed", "blocked"]:
            task = WorkstreamTask(id="t", description="d", assigned_agent="a", status=status)
            assert task.status == status


class TestPRReview:
    def test_pr_review_creation(self):
        """PRReview should create with defaults."""
        review = PRReview(reviewer="code_review_lead")
        assert review.reviewer == "code_review_lead"
        assert review.status == "pending"
        assert review.feedback is None
        assert review.rejection_reasons == []

    def test_pr_review_approved(self):
        """PRReview should accept approved status."""
        review = PRReview(
            reviewer="fe_reviewer",
            status="approved",
            feedback="LGTM",
        )
        assert review.status == "approved"
        assert review.feedback == "LGTM"

    def test_pr_review_rejected(self):
        """PRReview should accept rejection with reasons."""
        review = PRReview(
            reviewer="be_reviewer",
            status="rejected",
            feedback="Needs work",
            rejection_reasons=["Missing error handling", "No tests"],
        )
        assert review.status == "rejected"
        assert len(review.rejection_reasons) == 2


class TestCostSnapshot:
    def test_cost_snapshot_defaults(self):
        """CostSnapshot should initialize with zero values."""
        snap = CostSnapshot()
        assert snap.total_tokens_in == 0
        assert snap.total_tokens_out == 0
        assert snap.total_cost_usd == 0.0
        assert snap.hourly_rate == 0.0
        assert snap.budget_remaining == 0.0
        assert snap.by_model == {}
        assert snap.by_agent == {}

    def test_cost_snapshot_with_values(self):
        """CostSnapshot should store provided values."""
        snap = CostSnapshot(
            total_tokens_in=50000,
            total_tokens_out=20000,
            total_cost_usd=1.50,
            hourly_rate=0.75,
            budget_remaining=8.50,
            by_model={"sonnet": 1.0, "haiku": 0.5},
            by_agent={"eng1": 0.8, "eng2": 0.7},
        )
        assert snap.total_tokens_in == 50000
        assert snap.total_cost_usd == 1.50
        assert snap.by_model["sonnet"] == 1.0
        assert len(snap.by_agent) == 2
