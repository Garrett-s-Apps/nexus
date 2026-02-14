"""Tests for the LangGraph orchestrator graph construction and helpers."""

from src.orchestrator.graph import (
    _extract_criteria,
    _identify_parallel_groups,
    _infer_agent,
    _infer_language,
    _parse_budget,
    _parse_tasks,
    build_nexus_graph,
)
from src.orchestrator.state import WorkstreamTask


class TestBuildGraph:
    def test_graph_builds(self):
        graph = build_nexus_graph()
        assert graph is not None

    def test_graph_has_27_nodes(self):
        """Graph should have 27 nodes after adding approval gates, TDD, SDD workflows."""
        graph = build_nexus_graph()
        assert len(graph.nodes) == 27

    def test_graph_has_escalation_node(self):
        graph = build_nexus_graph()
        assert "escalation" in graph.nodes


class TestParseTasks:
    def test_parse_bullet_list(self):
        text = "- Build login page\n- Create API endpoint\n- Write tests"
        tasks = _parse_tasks(text, "em_frontend")
        assert len(tasks) == 3
        assert tasks[0].id == "em_frontend_1"

    def test_parse_numbered_list(self):
        text = "1. First task\n2. Second task"
        tasks = _parse_tasks(text, "em_backend")
        assert len(tasks) == 2

    def test_parse_json_array(self):
        text = '[{"id": "t1", "description": "Build auth", "assigned_agent": "backend_scripting", "language": "python"}]'
        tasks = _parse_tasks(text, "em_backend")
        assert len(tasks) == 1
        assert tasks[0].id == "t1"
        assert tasks[0].language == "python"

    def test_parse_json_with_surrounding_text(self):
        text = 'Here are the tasks:\n[{"id": "x1", "description": "Do stuff"}]\nDone!'
        tasks = _parse_tasks(text, "em_platform")
        assert len(tasks) == 1

    def test_empty_input(self):
        tasks = _parse_tasks("", "em_frontend")
        assert tasks == []


class TestIdentifyParallelGroups:
    def test_empty_tasks(self):
        assert _identify_parallel_groups([]) == []

    def test_single_em_sequential(self):
        tasks = [
            WorkstreamTask(id="em_frontend_1", description="t1", assigned_agent="fe"),
            WorkstreamTask(id="em_frontend_2", description="t2", assigned_agent="fe"),
        ]
        groups = _identify_parallel_groups(tasks)
        assert len(groups) == 2
        assert groups[0] == ["em_frontend_1"]
        assert groups[1] == ["em_frontend_2"]

    def test_multi_em_parallel(self):
        tasks = [
            WorkstreamTask(id="em_frontend_1", description="t1", assigned_agent="fe"),
            WorkstreamTask(id="em_backend_1", description="t2", assigned_agent="be"),
            WorkstreamTask(id="em_platform_1", description="t3", assigned_agent="devops"),
        ]
        groups = _identify_parallel_groups(tasks)
        assert len(groups) == 1
        assert len(groups[0]) == 3


class TestInferAgent:
    def test_frontend_em(self):
        assert _infer_agent("Build React component", "em_frontend") == "frontend_dev"

    def test_backend_em_default(self):
        assert _infer_agent("Create API endpoint", "em_backend") == "backend_scripting"

    def test_backend_em_jvm(self):
        assert _infer_agent("Build Java service", "em_backend") == "backend_jvm"

    def test_platform_em(self):
        assert _infer_agent("Set up CI/CD", "em_platform") == "devops_engineer"

    def test_unknown_em(self):
        assert _infer_agent("Something", "unknown") == "fullstack_dev"


class TestInferLanguage:
    def test_typescript(self):
        assert _infer_language("Build React component with TypeScript") == "typescript"

    def test_python(self):
        assert _infer_language("Create python FastAPI endpoint") == "python"

    def test_none_for_unknown(self):
        assert _infer_language("Do something") is None


class TestExtractCriteria:
    def test_bullet_list(self):
        text = "- Must handle auth\n- Must be fast\n- Must be secure"
        criteria = _extract_criteria(text)
        assert len(criteria) == 3

    def test_fallback_to_text(self):
        text = "Just one big paragraph with no bullets"
        criteria = _extract_criteria(text)
        assert len(criteria) == 1


class TestParseBudget:
    def test_parse_budget_lines(self):
        text = "Planning: $2.00\nImplementation: $5.00\nTesting: $1.50"
        budget = _parse_budget(text)
        assert budget["planning"] == 2.0
        assert budget["implementation"] == 5.0

    def test_empty_returns_empty_dict(self):
        budget = _parse_budget("No budget info here")
        assert budget == {}
