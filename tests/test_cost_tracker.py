"""Tests for NEXUS CostTracker — pricing, budgets, enforcement, and reporting."""

import time


class TestCalculateCost:
    def test_calculate_cost(self, cost_db):
        """Cost calculation should use per-model pricing per 1M tokens."""
        # Haiku: input=0.25/1M, output=1.25/1M
        cost = cost_db.calculate_cost("haiku", 1_000_000, 1_000_000)
        assert abs(cost - (0.25 + 1.25)) < 0.001

    def test_calculate_cost_sonnet(self, cost_db):
        """Sonnet pricing: input=3.0/1M, output=15.0/1M."""
        cost = cost_db.calculate_cost("sonnet", 500_000, 100_000)
        expected = (500_000 * 3.0 + 100_000 * 15.0) / 1_000_000
        assert abs(cost - expected) < 0.001

    def test_calculate_cost_unknown_model_falls_back_to_sonnet(self, cost_db):
        """Unknown models should default to sonnet pricing."""
        cost_unknown = cost_db.calculate_cost("unknown-model", 1000, 1000)
        cost_sonnet = cost_db.calculate_cost("sonnet", 1000, 1000)
        assert cost_unknown == cost_sonnet

    def test_calculate_cost_zero_tokens(self, cost_db):
        """Zero tokens should produce zero cost."""
        assert cost_db.calculate_cost("opus", 0, 0) == 0.0


class TestRecord:
    def test_record_updates_totals(self, cost_db):
        """Recording a cost event should update session totals."""
        cost_db.record("haiku", "eng1", 1000, 500)

        assert cost_db.session_cost > 0
        assert cost_db.call_count == 1
        assert "haiku" in cost_db.by_model
        assert "eng1" in cost_db.by_agent

    def test_record_by_project(self, cost_db):
        """Recording with a project should track per-project costs."""
        cost_db.record("sonnet", "eng1", 1000, 500, project="my-app")
        assert "my-app" in cost_db.by_project
        assert cost_db.by_project["my-app"] > 0

    def test_record_multiple_calls_accumulate(self, cost_db):
        """Multiple records should accumulate correctly."""
        cost_db.record("haiku", "eng1", 1000, 1000)
        cost_db.record("haiku", "eng1", 1000, 1000)
        assert cost_db.call_count == 2
        assert cost_db.session_cost > 0


class TestHourlyRate:
    def test_hourly_rate_calculation(self, cost_db):
        """Hourly rate should be zero when less than 60s have elapsed."""
        cost_db.record("opus", "eng1", 100000, 50000)
        # Session just started, less than 60s
        assert cost_db.hourly_rate == 0.0

    def test_hourly_rate_positive_after_elapsed(self, cost_db):
        """After enough time, hourly rate should be positive."""
        cost_db.session_start = time.time() - 3600  # 1 hour ago
        cost_db.record("opus", "eng1", 100000, 50000)
        assert cost_db.hourly_rate > 0


class TestBudgetEnforcement:
    def test_budget_enforcement_warning(self, cost_db):
        """Exceeding hourly target should produce a warning alert."""
        cost_db.session_start = time.time() - 3600
        cost_db.budgets["hourly_target"] = 0.001  # very low target

        actions = cost_db.record("opus", "eng1", 100000, 50000)
        assert len(actions["alerts"]) > 0
        assert any("hourly rate" in a.lower() for a in actions["alerts"])

    def test_budget_enforcement_downgrade(self, cost_db):
        """Exceeding hourly hard cap should trigger model downgrade."""
        cost_db.session_start = time.time() - 3600
        cost_db.budgets["hourly_hard_cap"] = 0.0001  # near-zero cap

        actions = cost_db.record("opus", "eng1", 1000000, 500000)
        assert actions["downgrade"] is True
        assert cost_db._downgrade_active is True

    def test_session_hard_cap(self, cost_db):
        """Exceeding session hard cap should trigger kill_session."""
        cost_db.budgets["session_hard_cap"] = 0.0001
        cost_db.session_start = time.time() - 3600  # ensure hourly calc works

        actions = cost_db.record("opus", "eng1", 10000000, 10000000)
        assert actions["kill_session"] is True


class TestEffectiveModel:
    def test_get_effective_model_normal(self, cost_db):
        """Under budget, effective model should be the requested model."""
        assert cost_db.get_effective_model("opus") == "opus"
        assert cost_db.get_effective_model("sonnet") == "sonnet"
        assert cost_db.get_effective_model("haiku") == "haiku"

    def test_get_effective_model_downgraded(self, cost_db):
        """When downgrade is active, models should be stepped down."""
        cost_db._downgrade_active = True
        assert cost_db.get_effective_model("opus") == "sonnet"
        assert cost_db.get_effective_model("sonnet") == "haiku"
        assert cost_db.get_effective_model("haiku") == "haiku"  # can't go lower


class TestReporting:
    def test_daily_breakdown(self, cost_db):
        """Daily breakdown should return aggregated cost data."""
        cost_db.record("haiku", "eng1", 10000, 5000)
        breakdown = cost_db.get_daily_breakdown(days=7)
        # Should have at least one day with data
        assert isinstance(breakdown, list)
        if breakdown:
            assert "date" in breakdown[0]
            assert "cost" in breakdown[0]
            assert "calls" in breakdown[0]

    def test_agent_breakdown(self, cost_db):
        """Agent breakdown should be sorted by spend descending."""
        cost_db.record("sonnet", "expensive_agent", 1000000, 500000)
        cost_db.record("haiku", "cheap_agent", 1000, 500)

        breakdown = cost_db.get_agent_breakdown()
        assert len(breakdown) == 2
        assert breakdown[0]["cost"] >= breakdown[1]["cost"]

    def test_cfo_report_generation(self, cost_db):
        """CFO report should be a formatted string with key sections."""
        cost_db.record("sonnet", "eng1", 10000, 5000, project="test")
        report = cost_db.generate_cfo_report()

        assert "CFO Cost Report" in report
        assert "SESSION" in report
        assert "MONTH-TO-DATE" in report
        assert "BY MODEL" in report
        assert "BY AGENT" in report

    def test_total_cost_property(self, cost_db):
        """total_cost should equal session_cost."""
        cost_db.record("haiku", "eng1", 10000, 5000)
        assert cost_db.total_cost == cost_db.session_cost

    def test_over_budget_property(self, cost_db):
        """over_budget should reflect hourly rate vs hard cap."""
        assert cost_db.over_budget is False
