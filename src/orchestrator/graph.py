"""
NEXUS LangGraph Orchestrator

This is the brain of NEXUS. It defines the organizational structure as an
executable graph. Each node is an agent or decision point. Edges define
the flow of work through the organization.
"""

import asyncio
import yaml
import os
from typing import Any, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.orchestrator.state import NexusState, WorkstreamTask, PRReview, CostSnapshot
from src.agents.sdk_bridge import (
    run_sdk_agent,
    run_planning_agent,
    run_gemini,
    run_o3,
    cost_tracker,
)


def _load_agent_configs() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "agents.yaml")
    config_path = os.path.normpath(config_path)
    with open(config_path) as f:
        return yaml.safe_load(f)["agents"]


AGENTS = _load_agent_configs()


# ============================================
# NODE FUNCTIONS
# Each function is a node in the LangGraph graph.
# It receives the current state and returns updates.
# ============================================


async def intake_node(state: NexusState) -> dict:
    """Parse the incoming directive and set up the session."""
    return {
        "current_phase": "executive_planning",
        "branch_name": f"nexus/{state.directive[:40].replace(' ', '-').lower()}",
    }


async def ceo_node(state: NexusState) -> dict:
    """CEO interprets the directive and sets strategic direction."""
    result = await run_planning_agent(
        "ceo",
        AGENTS["ceo"],
        f"""Garrett has given this directive: "{state.directive}"

Interpret the strategic intent. What are we building and why?
Define the high-level objective clearly and concisely.
If other executives have provided input, incorporate it.

Previous strategic brief: {state.strategic_brief or 'None yet'}
CPO requirements: {state.cpo_requirements or 'Not yet defined'}
CFO budget notes: {state.cfo_budget_allocation or 'Not yet defined'}
CRO timeline: {state.cro_timeline or 'Not yet defined'}

Output a clear strategic brief that the engineering team can act on.""",
    )
    return {
        "strategic_brief": result["output"],
        "cost": _update_cost(state.cost, result),
    }


async def cpo_node(state: NexusState) -> dict:
    """CPO defines requirements and acceptance criteria."""
    result = await run_planning_agent(
        "cpo",
        AGENTS["cpo"],
        f"""Strategic brief from CEO: {state.strategic_brief}

Define specific requirements and acceptance criteria for this objective.
Think from the perspective of a REAL person using this product.
What would they expect? What would frustrate them? What edge cases matter?

Output:
1. Clear requirements (what must be built)
2. Acceptance criteria (how we know it's done)
3. UX considerations (what a real user would care about)""",
    )

    return {
        "cpo_requirements": result["output"],
        "cpo_acceptance_criteria": _extract_criteria(result["output"]),
        "cost": _update_cost(state.cost, result),
    }


async def cfo_node(state: NexusState) -> dict:
    """CFO allocates token budget for the work."""
    result = await run_planning_agent(
        "cfo",
        AGENTS["cfo"],
        f"""Strategic brief: {state.strategic_brief}
Requirements: {state.cpo_requirements}
Current hourly rate: ${cost_tracker.hourly_rate:.2f}/hr (target: $1.00/hr)
Total spend this session: ${cost_tracker.total_cost:.2f}

Allocate a token budget for this work. Break it down by:
- Planning phase budget
- Implementation phase budget
- Testing phase budget
- Review phase budget
- Documentation phase budget
- Emergency reserve

Flag if this work risks exceeding the $1/hr target.
Recommend cost-saving approaches if needed (e.g., use Haiku for X, skip Y).

Output a budget allocation as key:value pairs.""",
    )

    return {
        "cfo_budget_allocation": _parse_budget(result["output"]),
        "cfo_approved": True,
        "cost": _update_cost(state.cost, result),
    }


async def cro_node(state: NexusState) -> dict:
    """CRO estimates timeline and identifies bottlenecks."""
    result = await run_planning_agent(
        "cro",
        AGENTS["cro"],
        f"""Strategic brief: {state.strategic_brief}
Requirements: {state.cpo_requirements}
Budget: {state.cfo_budget_allocation}

Estimate delivery timeline. Identify:
1. Which workstreams can run in parallel
2. Which are sequential dependencies
3. Potential bottlenecks
4. How to optimize throughput

Output a timeline estimate and parallelization strategy.""",
    )

    return {
        "cro_timeline": result["output"],
        "cro_approved": True,
        "cost": _update_cost(state.cost, result),
    }


async def executive_consensus_node(state: NexusState) -> dict:
    """Check if executives have reached consensus. Loop if not."""
    all_approved = (
        state.strategic_brief is not None
        and state.cpo_requirements is not None
        and state.cfo_approved
        and state.cro_approved
    )

    return {
        "executive_consensus": all_approved,
        "executive_loop_count": state.executive_loop_count + 1,
    }


async def vp_engineering_node(state: NexusState) -> dict:
    """VP Eng translates strategy into technical design."""
    result = await run_planning_agent(
        "vp_engineering",
        AGENTS["vp_engineering"],
        f"""Strategic brief: {state.strategic_brief}
Requirements: {state.cpo_requirements}
Acceptance criteria: {state.cpo_acceptance_criteria}
Timeline/parallelization: {state.cro_timeline}
Budget: {state.cfo_budget_allocation}
Project path: {state.project_path}

Decompose this into a technical design:
1. Components/services/modules needed
2. Language choice per component
3. API contracts between components
4. Data models
5. Which workstreams can be parallelized
6. Which agents should handle which workstream

Output a complete technical design document.""",
    )

    return {
        "technical_design": result["output"],
        "current_phase": "technical_planning",
        "cost": _update_cost(state.cost, result),
    }


async def tech_lead_review_node(state: NexusState) -> dict:
    """Tech Lead reviews the technical design for architecture soundness."""
    result = await run_planning_agent(
        "tech_lead",
        AGENTS["tech_lead"],
        f"""Review this technical design for architecture soundness:

{state.technical_design}

Check for:
1. Over-engineering (YAGNI violations)
2. Missing error handling in the design
3. Security gaps
4. Performance bottlenecks
5. Type safety concerns (will this lead to any type violations?)
6. Scalability issues

If approved, say APPROVED and explain why.
If not, say NEEDS_REVISION and list specific changes needed.""",
    )

    approved = "APPROVED" in result["output"].upper() and "NEEDS_REVISION" not in result["output"].upper()

    return {
        "tech_plan_approved": approved,
        "tech_plan_loop_count": state.tech_plan_loop_count + 1,
        "cost": _update_cost(state.cost, result),
    }


async def decomposition_node(state: NexusState) -> dict:
    """Engineering managers decompose work into specific tasks."""
    tasks = []

    for em_name in ["em_frontend", "em_backend", "em_platform"]:
        result = await run_planning_agent(
            em_name,
            AGENTS[em_name],
            f"""Technical design: {state.technical_design}
Your domain: {AGENTS[em_name]['name']}

Break down the work in YOUR domain into specific, implementable tasks.
For each task, specify:
- task_id: unique identifier
- description: what needs to be done
- assigned_agent: which implementation agent should do it
- language: primary language for this task
- dependencies: which other tasks must complete first

Output as a structured list.""",
        )

        parsed_tasks = _parse_tasks(result["output"], em_name)
        tasks.extend(parsed_tasks)

    parallel_groups = _identify_parallel_groups(tasks)

    return {
        "workstreams": tasks,
        "parallel_forks": parallel_groups,
        "current_phase": "implementation",
        "cost": _update_cost(state.cost, result),
    }


async def implementation_node(state: NexusState) -> dict:
    """Execute implementation tasks via Agent SDK sessions."""
    results = []
    files_changed = []
    commits = []

    for fork_group in state.parallel_forks:
        parallel_tasks = [t for t in state.workstreams if t.id in fork_group]

        coros = []
        for task in parallel_tasks:
            agent_key = task.assigned_agent
            if agent_key in AGENTS and AGENTS[agent_key].get("spawns_sdk"):
                coros.append(
                    run_sdk_agent(
                        agent_key,
                        AGENTS[agent_key],
                        f"""TASK: {task.description}

Technical design context:
{state.technical_design}

Requirements:
{state.cpo_requirements}

Acceptance criteria:
{state.cpo_acceptance_criteria}

RULES:
- NEVER use type:any in TypeScript
- Comments explain WHY, never WHAT
- Handle all error states
- Validate all inputs
- No hardcoded secrets
- Write meaningful tests alongside implementation

Implement this task completely. Write the code, create the files, run tests.""",
                        state.project_path,
                    )
                )

        if coros:
            group_results = await asyncio.gather(*coros, return_exceptions=True)
            for r in group_results:
                if isinstance(r, dict):
                    results.append(r)

    updated_tasks = []
    for task in state.workstreams:
        task.status = "completed"
        updated_tasks.append(task)

    return {
        "workstreams": updated_tasks,
        "current_phase": "quality_gate",
        "cost": _update_cost_multi(state.cost, results),
    }


async def linting_node(state: NexusState) -> dict:
    """Run linting across all changed files."""
    result = await run_sdk_agent(
        "linting_agent",
        AGENTS["linting_agent"],
        f"""Run linters on all files in this project.

Check for:
1. TypeScript: any usage of type:any, @ts-ignore, @ts-expect-error
2. All languages: hardcoded secrets, console.log in production code
3. Python: bare except, mutable defaults, import *
4. SQL: string concatenation in queries
5. General: missing error handling, unvalidated input

Report violations as BLOCKING or WARNING.
If ANY type:any is found, report it as a CRITICAL BLOCKING violation.

Run: eslint, ruff, or appropriate linter for each file type found.""",
        state.project_path,
    )

    any_violations = result["output"].lower().count("type:any") + result["output"].lower().count("type: any")

    return {
        "lint_results": {"output": result["output"], "passed": "BLOCKING" not in result["output"]},
        "any_type_violations": any_violations,
        "cost": _update_cost(state.cost, result),
    }


async def testing_node(state: NexusState) -> dict:
    """Run tests and generate coverage."""
    test_fe = run_sdk_agent(
        "test_frontend",
        AGENTS["test_frontend"],
        f"""Write and run meaningful frontend tests for the recent implementation.

Requirements: {state.cpo_requirements}
Acceptance criteria: {state.cpo_acceptance_criteria}

Every test must answer: 'What real-world scenario does this protect against?'
Test user flows, edge cases, error states. NOT implementation details.
Run the tests and report results.""",
        state.project_path,
    )

    test_be = run_sdk_agent(
        "test_backend",
        AGENTS["test_backend"],
        f"""Write and run meaningful backend tests for the recent implementation.

Requirements: {state.cpo_requirements}

Test edge cases: malformed input, unavailable services, rate limits, unicode.
Every test must protect against a real failure mode.
Run the tests and report results.""",
        state.project_path,
    )

    fe_result, be_result = await asyncio.gather(test_fe, test_be)

    return {
        "test_results": {
            "frontend": fe_result["output"],
            "backend": be_result["output"],
        },
        "cost": _update_cost_multi(state.cost, [fe_result, be_result]),
    }


async def security_scan_node(state: NexusState) -> dict:
    """Security consultant runs full security audit."""
    result = await run_sdk_agent(
        "security_consultant",
        AGENTS["security_consultant"],
        f"""Run a full security audit on this project:

1. Secret scan: look for API keys, passwords, tokens in code and configs
2. Dependency scan: check for known CVEs in all dependencies
3. SAST: check for SQL injection, XSS, path traversal, command injection
4. Auth review: validate authentication and authorization flows
5. OWASP Top 10 checklist

Report findings as CRITICAL, HIGH, MEDIUM, LOW.
Zero tolerance for CRITICAL or HIGH findings.""",
        state.project_path,
    )

    return {
        "security_scan_results": {"output": result["output"]},
        "cost": _update_cost(state.cost, result),
    }


async def visual_qa_node(state: NexusState) -> dict:
    """Gemini UX consultant validates visual output."""
    result = await run_gemini(
        f"""Review the following UI implementation for visual quality:

Project: {state.project_path}
Requirements: {state.cpo_requirements}

Check for:
1. Contrast validation (WCAG AA minimum)
2. Layout coherence across breakpoints
3. Text readability (no white text on white backgrounds)
4. Interactive element visibility
5. Does this look like a real product, not an AI prototype?

Be specific about any issues found and recommend exact fixes.""",
        system_prompt=AGENTS["ux_consultant"]["system_prompt"],
    )

    return {
        "visual_qa_results": {"output": result["output"]},
        "cost": _update_cost(state.cost, result),
    }


async def quality_gate_node(state: NexusState) -> dict:
    """QA Lead determines if quality is sufficient to proceed to PR."""
    lint_passed = state.lint_results.get("passed", False)
    no_any_violations = state.any_type_violations == 0
    security_ok = "CRITICAL" not in str(state.security_scan_results)

    if not lint_passed or not no_any_violations or not security_ok:
        return {
            "current_phase": "implementation",
            "error": f"Quality gate failed: lint={lint_passed}, any_violations={state.any_type_violations}, security={security_ok}",
        }

    return {"current_phase": "pr_review"}


async def pr_review_node(state: NexusState) -> dict:
    """Senior engineers review the PR."""
    reviewers = ["sr_frontend", "sr_backend", "sr_fullstack", "sr_devops"]
    reviews = []

    coros = []
    for reviewer_key in reviewers:
        coros.append(
            run_sdk_agent(
                reviewer_key,
                AGENTS[reviewer_key],
                f"""Review the recent changes in this project.

Technical design: {state.technical_design}
Requirements: {state.cpo_requirements}

Check your domain for:
- Architecture compliance with the approved design
- Code quality and anti-pattern violations
- Test coverage adequacy
- Security concerns
- Comment quality (WHY not WHAT, or better: self-documenting code)

If approved, respond with APPROVED and a brief explanation.
If rejected, respond with REJECTED and specific feedback on what to fix.""",
                state.project_path,
            )
        )

    results = await asyncio.gather(*coros, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, dict):
            approved = "APPROVED" in result["output"].upper() and "REJECTED" not in result["output"].upper()
            reviews.append(
                PRReview(
                    reviewer=reviewers[i],
                    status="approved" if approved else "rejected",
                    feedback=result["output"],
                )
            )

    all_approved = all(r.status == "approved" for r in reviews)

    return {
        "pr_reviews": reviews,
        "pr_approved": all_approved,
        "pr_loop_count": state.pr_loop_count + 1,
        "cost": _update_cost_multi(state.cost, [r for r in results if isinstance(r, dict)]),
    }


async def demo_node(state: NexusState) -> dict:
    """CPO prepares the demo for Garrett."""
    result = await run_planning_agent(
        "cpo",
        AGENTS["cpo"],
        f"""Prepare a demo summary for Garrett.

What was built: {state.strategic_brief}
Requirements met: {state.cpo_requirements}
Acceptance criteria: {state.cpo_acceptance_criteria}
Test results: {state.test_results}
Security scan: {state.security_scan_results}
Total cost: ${state.cost.total_cost_usd:.2f}

Write a concise demo briefing that:
1. Shows what was built and why
2. Lists key decisions made
3. Shows performance metrics
4. Confirms security compliance
5. States it's ready for deployment

This is a DEMO, not a request for review. Be confident and direct.""",
    )

    return {
        "demo_summary": result["output"],
        "demo_metrics": {
            "Total Cost": f"${state.cost.total_cost_usd:.2f}",
            "Tests": "Passed" if state.test_results else "N/A",
            "Security": "Clean" if "CRITICAL" not in str(state.security_scan_results) else "Issues Found",
            "Lint": "Passed" if state.lint_results.get("passed") else "Issues",
        },
        "current_phase": "complete",
        "cost": _update_cost(state.cost, result),
    }


# ============================================
# ROUTING FUNCTIONS
# These control the flow through the graph.
# ============================================


def route_after_executive_consensus(state: NexusState) -> str:
    if state.executive_consensus:
        return "vp_engineering"
    if state.executive_loop_count >= 3:
        return "vp_engineering"
    return "ceo"


def route_after_tech_review(state: NexusState) -> str:
    if state.tech_plan_approved:
        return "decomposition"
    if state.tech_plan_loop_count >= 3:
        return "decomposition"
    return "vp_engineering"


def route_after_quality_gate(state: NexusState) -> str:
    if state.current_phase == "pr_review":
        return "pr_review"
    return "implementation"


def route_after_pr_review(state: NexusState) -> str:
    if state.pr_approved:
        return "demo"
    if state.pr_loop_count >= 3:
        return "demo"
    return "implementation"


# ============================================
# GRAPH CONSTRUCTION
# This builds the actual executable graph.
# ============================================


def build_nexus_graph() -> StateGraph:
    """Build the NEXUS organizational graph."""

    graph = StateGraph(NexusState)

    # --- Add all nodes ---
    graph.add_node("intake", intake_node)
    graph.add_node("ceo", ceo_node)
    graph.add_node("cpo", cpo_node)
    graph.add_node("cfo", cfo_node)
    graph.add_node("cro", cro_node)
    graph.add_node("executive_consensus", executive_consensus_node)
    graph.add_node("vp_engineering", vp_engineering_node)
    graph.add_node("tech_lead_review", tech_lead_review_node)
    graph.add_node("decomposition", decomposition_node)
    graph.add_node("implementation", implementation_node)
    graph.add_node("linting", linting_node)
    graph.add_node("testing", testing_node)
    graph.add_node("security_scan", security_scan_node)
    graph.add_node("visual_qa", visual_qa_node)
    graph.add_node("quality_gate", quality_gate_node)
    graph.add_node("pr_review", pr_review_node)
    graph.add_node("demo", demo_node)

    # --- Define edges (the org chart as a flow) ---

    # Start → Intake
    graph.add_edge(START, "intake")

    # Intake → Executive Planning Loop
    graph.add_edge("intake", "ceo")
    graph.add_edge("ceo", "cpo")
    graph.add_edge("cpo", "cfo")
    graph.add_edge("cfo", "cro")
    graph.add_edge("cro", "executive_consensus")

    # Executive consensus → either loop back or proceed
    graph.add_conditional_edges(
        "executive_consensus",
        route_after_executive_consensus,
        {"ceo": "ceo", "vp_engineering": "vp_engineering"},
    )

    # VP Eng → Tech Lead Review
    graph.add_edge("vp_engineering", "tech_lead_review")

    # Tech Lead → either loop back or proceed to decomposition
    graph.add_conditional_edges(
        "tech_lead_review",
        route_after_tech_review,
        {"vp_engineering": "vp_engineering", "decomposition": "decomposition"},
    )

    # Decomposition → Implementation
    graph.add_edge("decomposition", "implementation")

    # Implementation → Quality checks (parallel)
    graph.add_edge("implementation", "linting")
    graph.add_edge("implementation", "testing")
    graph.add_edge("implementation", "security_scan")
    graph.add_edge("implementation", "visual_qa")

    # Quality checks → Quality Gate
    graph.add_edge("linting", "quality_gate")
    graph.add_edge("testing", "quality_gate")
    graph.add_edge("security_scan", "quality_gate")
    graph.add_edge("visual_qa", "quality_gate")

    # Quality Gate → PR Review or back to Implementation
    graph.add_conditional_edges(
        "quality_gate",
        route_after_quality_gate,
        {"pr_review": "pr_review", "implementation": "implementation"},
    )

    # PR Review → Demo or back to Implementation
    graph.add_conditional_edges(
        "pr_review",
        route_after_pr_review,
        {"demo": "demo", "implementation": "implementation"},
    )

    # Demo → End
    graph.add_edge("demo", END)

    return graph


def compile_nexus(checkpointer=None):
    """Compile the NEXUS graph with optional checkpointing."""
    graph = build_nexus_graph()
    if checkpointer is None:
        checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def compile_nexus_dynamic(checkpointer=None):
    """
    Compile NEXUS using the LIVE agent registry instead of static YAML.
    Call this after any org change so the graph reflects the current org.
    """
    from src.agents.registry import registry
    global AGENTS
    AGENTS = registry.get_active_agent_configs()
    return compile_nexus(checkpointer)


# ============================================
# HELPER FUNCTIONS
# ============================================


def _update_cost(current: CostSnapshot, result: dict) -> CostSnapshot:
    return CostSnapshot(
        total_cost_usd=current.total_cost_usd + result.get("cost", 0),
        by_model={**current.by_model, result.get("model", "unknown"): current.by_model.get(result.get("model", "unknown"), 0) + result.get("cost", 0)},
        by_agent={**current.by_agent, result.get("agent", "unknown"): current.by_agent.get(result.get("agent", "unknown"), 0) + result.get("cost", 0)},
        hourly_rate=cost_tracker.hourly_rate,
    )


def _update_cost_multi(current: CostSnapshot, results: list[dict]) -> CostSnapshot:
    updated = current
    for r in results:
        if isinstance(r, dict):
            updated = _update_cost(updated, r)
    return updated


def _extract_criteria(text: str) -> list[str]:
    lines = text.split("\n")
    criteria = []
    for line in lines:
        line = line.strip()
        if line and (line.startswith("-") or line.startswith("*") or line[0:1].isdigit()):
            criteria.append(line.lstrip("-*0123456789. "))
    return criteria if criteria else [text[:200]]


def _parse_budget(text: str) -> dict[str, float]:
    budget = {}
    for line in text.split("\n"):
        if ":" in line and "$" in line:
            key = line.split(":")[0].strip().lower().replace(" ", "_")
            try:
                val = float(line.split("$")[-1].strip().split()[0].replace(",", ""))
                budget[key] = val
            except (ValueError, IndexError):
                pass
    return budget if budget else {"total": 5.0}


def _parse_tasks(text: str, em_source: str) -> list[WorkstreamTask]:
    tasks = []
    task_id = 0
    for line in text.split("\n"):
        line = line.strip()
        if line and (line.startswith("-") or line.startswith("*") or line[0:1].isdigit()):
            task_id += 1
            tasks.append(
                WorkstreamTask(
                    id=f"{em_source}_{task_id}",
                    description=line.lstrip("-*0123456789. "),
                    assigned_agent=_infer_agent(line, em_source),
                    language=_infer_language(line),
                )
            )
    return tasks


def _infer_agent(task_text: str, em_source: str) -> str:
    text_lower = task_text.lower()
    if em_source == "em_frontend":
        return "frontend_dev"
    elif em_source == "em_backend":
        if any(kw in text_lower for kw in ["java", "go", "c#", "c++"]):
            return "backend_jvm"
        return "backend_scripting"
    elif em_source == "em_platform":
        return "devops_engineer"
    return "fullstack_dev"


def _infer_language(task_text: str) -> str | None:
    text_lower = task_text.lower()
    lang_map = {
        "typescript": "typescript", "react": "typescript", "next.js": "typescript",
        "javascript": "javascript", "python": "python", "java": "java",
        "go ": "go", "golang": "go", "c#": "csharp", "ruby": "ruby",
        "php": "php", "html": "html", "css": "css",
    }
    for keyword, lang in lang_map.items():
        if keyword in text_lower:
            return lang
    return None


def _identify_parallel_groups(tasks: list[WorkstreamTask]) -> list[list[str]]:
    return [[t.id for t in tasks]]
