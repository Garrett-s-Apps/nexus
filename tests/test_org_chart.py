"""Tests for NEXUS Org Chart — agent definitions, model costs, and org structure."""

from src.agents.org_chart import (
    MODEL_COSTS, OPUS, SONNET, HAIKU, O3,
    get_org_summary,
)
from src.agents.registry import registry


class TestOrgChartStructure:
    def test_org_chart_has_all_agents(self):
        """Registry should contain all expected agent categories."""
        # Ensure registry is initialized
        if not registry.is_initialized():
            registry.load_from_yaml()

        expected_roles = [
            "vp_product", "pm_1", "vp_engineering", "chief_architect",
            "eng_lead", "fe_engineer_1", "be_engineer_1",
            "qa_lead", "ciso", "head_of_docs", "director_analytics",
        ]
        for role in expected_roles:
            assert registry.get_agent(role) is not None, f"Missing agent: {role}"

    def test_agent_count(self):
        """Should have a reasonable number of agents (20+)."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        agents = registry.get_active_agents()
        assert len(agents) >= 20

    def test_all_agents_have_required_fields(self):
        """Every agent should have name, model, description, reports_to, and layer."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        agents = registry.get_active_agents()
        for agent in agents:
            assert agent.name, f"Agent {agent.id} missing name"
            assert agent.model, f"Agent {agent.id} missing model"
            assert agent.description, f"Agent {agent.id} missing description"
            assert agent.layer, f"Agent {agent.id} missing layer"
            # reports_to can be None for CEO

    def test_agent_names_are_unique(self):
        """Agent names should be unique across the org chart."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        agents = registry.get_active_agents()
        names = [a.name for a in agents]
        assert len(names) == len(set(names)), f"Duplicate names found: {[n for n in names if names.count(n) > 1]}"


class TestModelCosts:
    def test_model_costs_defined(self):
        """MODEL_COSTS should have pricing for all model tiers."""
        assert HAIKU in MODEL_COSTS
        assert SONNET in MODEL_COSTS
        assert OPUS in MODEL_COSTS
        assert O3 in MODEL_COSTS

    def test_model_costs_have_input_output(self):
        """Each model cost entry should have input and output pricing."""
        for model, costs in MODEL_COSTS.items():
            assert "input" in costs, f"{model} missing input cost"
            assert "output" in costs, f"{model} missing output cost"
            assert costs["input"] >= 0
            assert costs["output"] >= 0

    def test_model_cost_ordering(self):
        """More powerful models should cost more."""
        assert MODEL_COSTS[HAIKU]["input"] < MODEL_COSTS[SONNET]["input"]
        assert MODEL_COSTS[SONNET]["input"] < MODEL_COSTS[OPUS]["input"]

    def test_all_agents_use_valid_models(self):
        """Every agent's model should be in the MODEL_COSTS dictionary."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        agents = registry.get_active_agents()
        valid_models = set(MODEL_COSTS.keys())
        for agent in agents:
            assert agent.model in valid_models, f"Agent {agent.id} uses unknown model: {agent.model}"


class TestOrgsGrouping:
    def test_orgs_grouping(self):
        """Registry should group agents by layer (org)."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        expected_layers = {"product", "engineering", "security", "documentation", "analytics"}
        for layer in expected_layers:
            agents = registry.get_agents_by_layer(layer)
            assert len(agents) > 0, f"Layer {layer} has no members"

    def test_all_agents_in_a_layer(self):
        """Every agent should belong to a layer."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        agents = registry.get_active_agents()
        for agent in agents:
            assert agent.layer, f"Agent {agent.id} has no layer"

    def test_engineering_is_largest_org(self):
        """Engineering should have the most members."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        eng_agents = registry.get_agents_by_layer("engineering")
        eng_count = len(eng_agents)

        for layer_name in ["product", "security", "documentation", "analytics", "salesforce"]:
            layer_agents = registry.get_agents_by_layer(layer_name)
            assert eng_count >= len(layer_agents), f"{layer_name} is larger than engineering"


class TestLeadershipAndICs:
    def test_leadership_and_ics(self):
        """Some agents should have direct reports (leaders), others should not (ICs)."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        agents = registry.get_active_agents()

        leaders = []
        ics = []
        for agent in agents:
            direct_reports = registry.get_direct_reports(agent.id)
            if direct_reports:
                leaders.append(agent)
            else:
                ics.append(agent)

        assert len(leaders) > 0, "Should have some leaders with direct reports"
        assert len(ics) > 0, "Should have some individual contributors"

    def test_leadership_plus_ics_equals_total(self):
        """Leadership + ICs should account for all agents."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        agents = registry.get_active_agents()

        leaders_count = sum(1 for a in agents if registry.get_direct_reports(a.id))
        ics_count = sum(1 for a in agents if not registry.get_direct_reports(a.id))

        assert leaders_count + ics_count == len(agents)

    def test_direct_reports_reference_valid_agents(self):
        """All direct_reports should reference valid agent IDs."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        agents = registry.get_active_agents()

        for agent in agents:
            direct_reports = registry.get_direct_reports(agent.id)
            for report in direct_reports:
                assert registry.get_agent(report.id) is not None, \
                    f"Agent {agent.id} has invalid direct report: {report.id}"

    def test_reports_to_references_valid_agents(self):
        """All reports_to should reference valid agent IDs or be None (for CEO)."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        agents = registry.get_active_agents()

        for agent in agents:
            if agent.reports_to is not None:
                assert registry.get_agent(agent.reports_to) is not None, \
                    f"Agent {agent.id} reports to invalid: {agent.reports_to}"


class TestGetOrgSummary:
    def test_get_org_summary(self):
        """get_org_summary should return a formatted string with key sections."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        summary = get_org_summary()

        assert "NEXUS" in summary
        assert "PRODUCT" in summary or "product" in summary
        assert "ENGINEERING" in summary or "engineering" in summary
        assert "SECURITY" in summary or "security" in summary
        assert "DOCUMENTATION" in summary or "documentation" in summary
        assert "ANALYTICS" in summary or "analytics" in summary
        assert "Total headcount:" in summary or "Total active agents:" in summary

    def test_org_summary_includes_all_agents(self):
        """The summary should mention all agents by name."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        summary = get_org_summary()
        agents = registry.get_active_agents()
        for agent in agents:
            assert agent.name in summary, f"Agent {agent.name} not in summary"

    def test_org_summary_includes_model_tiers(self):
        """The summary should show model tier labels."""
        if not registry.is_initialized():
            registry.load_from_yaml()
        summary = get_org_summary()
        assert "Sonnet" in summary or "sonnet" in summary
        assert "Haiku" in summary or "haiku" in summary
