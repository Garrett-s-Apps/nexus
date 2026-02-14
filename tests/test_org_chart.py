"""Tests for NEXUS Org Chart — agent definitions, model costs, and org structure."""

from src.agents.org_chart import (
    ORG_CHART, ALL_AGENT_IDS, ORGS, LEADERSHIP, ICS,
    MODEL_COSTS, OPUS, SONNET, HAIKU, O3,
    get_org_summary,
)


class TestOrgChartStructure:
    def test_org_chart_has_all_agents(self):
        """ORG_CHART should contain all expected agent categories."""
        # Check for key roles across orgs
        expected_roles = [
            "vp_product", "pm_1", "vp_engineering", "chief_architect",
            "eng_lead", "fe_engineer_1", "be_engineer_1",
            "qa_lead", "ciso", "head_of_docs", "director_analytics",
        ]
        for role in expected_roles:
            assert role in ORG_CHART, f"Missing agent: {role}"

    def test_agent_count(self):
        """Should have a reasonable number of agents (20+)."""
        assert len(ORG_CHART) >= 20
        assert len(ALL_AGENT_IDS) == len(ORG_CHART)

    def test_all_agents_have_required_fields(self):
        """Every agent should have name, title, model, role, reports_to, and org."""
        required_fields = {"name", "title", "model", "role", "reports_to", "org", "direct_reports"}
        for agent_id, cfg in ORG_CHART.items():
            for field in required_fields:
                assert field in cfg, f"Agent {agent_id} missing field: {field}"

    def test_all_agents_have_produces(self):
        """Every agent should have a 'produces' list."""
        for agent_id, cfg in ORG_CHART.items():
            assert "produces" in cfg, f"Agent {agent_id} missing 'produces'"
            assert isinstance(cfg["produces"], list)
            assert len(cfg["produces"]) > 0

    def test_agent_names_are_unique(self):
        """Agent names should be unique across the org chart."""
        names = [cfg["name"] for cfg in ORG_CHART.values()]
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
        valid_models = set(MODEL_COSTS.keys())
        for agent_id, cfg in ORG_CHART.items():
            assert cfg["model"] in valid_models, f"Agent {agent_id} uses unknown model: {cfg['model']}"


class TestOrgsGrouping:
    def test_orgs_grouping(self):
        """ORGS should group agents by organization."""
        expected_orgs = {"product", "engineering", "security", "documentation", "analytics"}
        for org in expected_orgs:
            assert org in ORGS, f"Missing org: {org}"
            assert len(ORGS[org]) > 0, f"Org {org} has no members"

    def test_all_agents_in_an_org(self):
        """Every agent should belong to exactly one org."""
        all_in_orgs = set()
        for org_members in ORGS.values():
            all_in_orgs.update(org_members)

        for agent_id in ALL_AGENT_IDS:
            assert agent_id in all_in_orgs, f"Agent {agent_id} not in any org"

    def test_engineering_is_largest_org(self):
        """Engineering should have the most members."""
        eng_count = len(ORGS.get("engineering", []))
        for org_name, members in ORGS.items():
            if org_name != "engineering":
                assert eng_count >= len(members), f"{org_name} is larger than engineering"


class TestLeadershipAndICs:
    def test_leadership_and_ics(self):
        """LEADERSHIP should contain agents with direct_reports; ICS should not."""
        assert len(LEADERSHIP) > 0
        assert len(ICS) > 0

        for leader_id in LEADERSHIP:
            cfg = ORG_CHART[leader_id]
            assert len(cfg["direct_reports"]) > 0, f"Leader {leader_id} has no direct reports"

        for ic_id in ICS:
            cfg = ORG_CHART[ic_id]
            assert len(cfg["direct_reports"]) == 0, f"IC {ic_id} has direct reports"

    def test_leadership_plus_ics_equals_total(self):
        """Leadership + ICs should account for all agents."""
        assert len(LEADERSHIP) + len(ICS) == len(ORG_CHART)

    def test_direct_reports_reference_valid_agents(self):
        """All direct_reports should reference valid agent IDs."""
        for agent_id, cfg in ORG_CHART.items():
            for report_id in cfg["direct_reports"]:
                assert report_id in ORG_CHART, f"Agent {agent_id} has invalid direct report: {report_id}"

    def test_reports_to_references_valid_agents(self):
        """All reports_to should reference valid agent IDs or 'ceo'."""
        for agent_id, cfg in ORG_CHART.items():
            reports_to = cfg["reports_to"]
            assert reports_to == "ceo" or reports_to in ORG_CHART, \
                f"Agent {agent_id} reports to invalid: {reports_to}"


class TestGetOrgSummary:
    def test_get_org_summary(self):
        """get_org_summary should return a formatted string with key sections."""
        summary = get_org_summary()

        assert "NEXUS VIRTUAL COMPANY" in summary
        assert "CEO: Garrett Eaglin" in summary
        assert "PRODUCT" in summary
        assert "ENGINEERING" in summary
        assert "SECURITY" in summary
        assert "DOCUMENTATION" in summary
        assert "ANALYTICS" in summary
        assert "Total headcount:" in summary

    def test_org_summary_includes_all_agents(self):
        """The summary should mention all agents by name."""
        summary = get_org_summary()
        for agent_id, cfg in ORG_CHART.items():
            assert cfg["name"] in summary, f"Agent {cfg['name']} not in summary"

    def test_org_summary_includes_model_tiers(self):
        """The summary should show model tier labels."""
        summary = get_org_summary()
        assert "Sonnet" in summary
        assert "Haiku" in summary
