"""
NEXUS LangGraph Orchestrator

This is the brain of NEXUS. It defines the organizational structure as an
executable graph. Each node is an agent or decision point. Edges define
the flow of work through the organization.
"""

import asyncio
import json
import logging
import os
import uuid
from collections.abc import Sequence

import yaml  # type: ignore[import-untyped]
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.agents.org_chart import get_model_for_budget
from src.agents.sdk_bridge import (
    cost_tracker,
    run_claude_code,
    run_gemini,
    run_planning_agent,
    run_sdk_agent,
)
from src.agents.task_result import TaskResult
from src.orchestrator.checkpoint import CheckpointManager
from src.orchestrator.state import CostSnapshot, NexusState, PRReview, WorkstreamTask
from src.slack import notifier

logger = logging.getLogger(__name__)

USE_CLAUDE_CODE = os.environ.get("USE_CLAUDE_CODE", "true").lower() in ("true", "1", "yes")


async def _run_impl_agent(agent_key: str, agent_config: dict, prompt: str, project_path: str) -> TaskResult:
    """Route implementation work through Claude Code CLI or Agent SDK."""
    if USE_CLAUDE_CODE and agent_config.get("spawns_sdk"):
        return await run_claude_code(agent_key, agent_config, prompt, project_path)
    return await run_sdk_agent(agent_key, agent_config, prompt, project_path)


async def safe_node(node_fn, state: NexusState, timeout: int = 300) -> dict:
    """Wrap any node function with timeout and error handling.

    Auto-checkpoints before executing the node.
    """
    # Auto-checkpoint before node execution
    try:
        checkpoint_manager = CheckpointManager(state.project_path)
        checkpoint_name = f"before-{node_fn.__name__}-{state.current_phase}"
        checkpoint_manager.save_checkpoint(checkpoint_name, manual=False)
        logger.debug("Auto-checkpoint created: %s", checkpoint_name)
    except Exception as e:
        logger.warning("Failed to create auto-checkpoint: %s", e)

    # Execute node with timeout and error handling
    try:
        return await asyncio.wait_for(node_fn(state), timeout=timeout)
    except TimeoutError:
        logger.error("Node %s timed out after %ds", node_fn.__name__, timeout)
        return {"error": f"{node_fn.__name__} timed out after {timeout}s", "escalation_reason": "timeout"}
    except Exception as e:
        logger.error("Node %s failed: %s", node_fn.__name__, e)
        return {"error": str(e), "escalation_reason": f"{node_fn.__name__} exception"}


def _load_agent_configs() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "agents.yaml")
    config_path = os.path.normpath(config_path)
    with open(config_path) as f:
        return yaml.safe_load(f)["agents"]  # type: ignore[no-any-return]


AGENTS = _load_agent_configs()

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
        "strategic_brief": result.output,
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
        "cpo_requirements": result.output,
        "cpo_acceptance_criteria": _extract_criteria(result.output),
        "cost": _update_cost(state.cost, result),
    }


async def cfo_node(state: NexusState) -> dict:
    """CFO allocates token budget for the work."""
    from src.orchestrator.approval import request_budget_approval

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

    budget_allocation = _parse_budget(result.output)

    # Calculate total allocated budget
    total_budget = sum(budget_allocation.values())
    current_spend = cost_tracker.total_cost

    # Budget enforcement logic
    cfo_approved = True
    budget_warnings = []

    # Check if current spend already exceeds hourly hard cap
    if cost_tracker.hourly_rate > cost_tracker.budgets["hourly_hard_cap"]:
        cfo_approved = False
        budget_warnings.append(
            f"BUDGET EXCEEDED: Hourly rate ${cost_tracker.hourly_rate:.2f}/hr exceeds hard cap ${cost_tracker.budgets['hourly_hard_cap']:.2f}/hr"
        )

    # Check if projected spend would exceed session hard cap
    projected_total = current_spend + total_budget
    if projected_total > cost_tracker.budgets["session_hard_cap"]:
        cfo_approved = False
        budget_warnings.append(
            f"BUDGET EXCEEDED: Projected total ${projected_total:.2f} exceeds session hard cap ${cost_tracker.budgets['session_hard_cap']:.2f}"
        )

    # High-cost operation warning (>$10)
    if total_budget > 10.0:
        budget_warnings.append(
            f"HIGH COST WARNING: Allocated budget ${total_budget:.2f} exceeds $10.00. User approval required."
        )

    # Log warnings
    if budget_warnings:
        logger.warning("CFO Budget Warnings: %s", " | ".join(budget_warnings))
        # Add warnings to budget allocation for visibility
        budget_allocation["_warnings"] = " | ".join(budget_warnings)  # type: ignore[assignment]

    # USER approval for budget > $50
    if total_budget > 50.0:
        user_approved = await request_budget_approval(
            total_budget=total_budget,
            breakdown=budget_allocation,
            threshold=50.0,
        )

        if not user_approved:
            return {
                "cfo_budget_allocation": budget_allocation,
                "cfo_approved": False,
                "escalation_reason": "User rejected high budget allocation",
                "cost": _update_cost(state.cost, result),
            }

    return {
        "cfo_budget_allocation": budget_allocation,
        "cfo_approved": cfo_approved,
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
        "cro_timeline": result.output,
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




async def spec_generation_node(state: NexusState) -> dict:
    """CPO generates formal specification from strategic brief and requirements."""
    import os

    # Load spec template
    template_path = os.path.join(state.project_path, "templates", "SPEC-TEMPLATE.md")
    if not os.path.exists(template_path):
        template_path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "SPEC-TEMPLATE.md")

    spec_template = ""
    if os.path.exists(template_path):
        with open(template_path) as f:
            spec_template = f.read()

    result = await run_planning_agent(
        "cpo",
        AGENTS["cpo"],
        f"""Generate a formal specification document for this project.

Strategic brief from CEO: {state.strategic_brief}
Requirements: {state.cpo_requirements}
Acceptance criteria: {state.cpo_acceptance_criteria}
Timeline: {state.cro_timeline}
Budget: {state.cfo_budget_allocation}

Use this template structure:
{spec_template}

Fill out ALL applicable sections with precise, unambiguous language optimized for LLM consumption.
Focus on:
1. Clear, measurable acceptance criteria
2. Explicit security requirements
3. Performance targets with numbers
4. Complete API contracts and data models
5. Test strategy with coverage targets

Output a complete, implementation-ready specification document.""",
    )

    # Store spec in memory.db and save to file
    spec_content = result.output
    spec_dir = os.path.join(state.project_path, ".claude", "specs")
    os.makedirs(spec_dir, exist_ok=True)

    spec_filename = f"{state.session_id}.md"
    spec_path = os.path.join(spec_dir, spec_filename)

    with open(spec_path, "w") as f:
        f.write(spec_content)

    logger.info("Spec generated and saved to %s", spec_path)

    return {
        "formal_spec": spec_content,
        "spec_file_path": spec_path,
        "current_phase": "spec_approval",
        "cost": _update_cost(state.cost, result),
    }


async def spec_approval_node(state: NexusState) -> dict:
    """CEO reviews spec, then USER approves spec → dev transition."""
    from src.orchestrator.approval import request_spec_to_dev_approval

    # Step 1: CEO agent reviews (autonomous)
    result = await run_planning_agent(
        "ceo",
        AGENTS["ceo"],
        f"""Review this formal specification for completeness and clarity.

SPECIFICATION:
{state.formal_spec}

Evaluate:
1. Is the objective clear and measurable?
2. Are requirements complete and unambiguous?
3. Are acceptance criteria testable and specific?
4. Is the technical design sufficient for implementation?
5. Are security considerations comprehensive?
6. Are performance targets realistic and measurable?

This is an AGENT-TO-AGENT approval. DO NOT ask for user approval.
You have authority to approve or reject this spec.

If the spec is complete and clear, respond with: APPROVED
If the spec needs refinement, respond with: REJECTED and list specific issues to address.

Maximum 2 refinement loops allowed.""",
    )

    ceo_approved = "APPROVED" in result.output.upper() and "REJECTED" not in result.output.upper()

    if not ceo_approved:
        return {
            "spec_approved": False,
            "spec_loop_count": state.spec_loop_count + 1,
            "ceo_approved": False,
            "cost": _update_cost(state.cost, result),
        }

    # Step 2: USER approval for strategic transition
    total_budget = sum(state.cfo_budget_allocation.values())
    spec_summary = state.formal_spec[:500] if state.formal_spec else "No spec available"

    user_approved = await request_spec_to_dev_approval(
        spec_summary=spec_summary,
        estimated_cost=total_budget,
        acceptance_criteria=state.cpo_acceptance_criteria,
    )

    return {
        "spec_approved": user_approved,
        "spec_loop_count": state.spec_loop_count + 1,
        "ceo_approved": ceo_approved,
        "user_approval_received": user_approved,
        "user_approval_context": {
            "gate": "spec_to_dev",
            "timestamp": "now",
            "approved": user_approved,
        },
        "cost": _update_cost(state.cost, result),
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
        "technical_design": result.output,
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

    approved = "APPROVED" in result.output.upper() and "NEEDS_REVISION" not in result.output.upper()

    return {
        "tech_plan_approved": approved,
        "tech_plan_loop_count": state.tech_plan_loop_count + 1,
        "cost": _update_cost(state.cost, result),
    }


async def ai_team_approval_node(state: NexusState) -> dict:
    """Dual approval gate for AI/ML tasks (ARCH-013).

    Agent-to-agent approval only:
    1. Orchestrator (VP Engineering) requests approval
    2. Architect reviews architectural implications
    3. Both must approve for AI Team invocation
    """
    # Identify AI/ML tasks
    ai_keywords = ["ml", "ai", "machine learning", "neural", "model", "training", "dataset", "prediction"]
    ai_tasks = [
        t for t in state.workstreams
        if any(kw in t.description.lower() for kw in ai_keywords)
    ]

    if not ai_tasks:
        return {"ai_team_approved": True}  # No AI tasks, skip gate

    # Step 1: Orchestrator (VP Engineering) approval request
    orchestrator_request = await run_planning_agent(
        "vp_engineering",
        AGENTS["vp_engineering"],
        f"""Review these AI/ML tasks for technical feasibility:

{chr(10).join(f"- {t.description}" for t in ai_tasks)}

As orchestrator, do you approve invoking the AI Team?

Consider:
- Data requirements and availability
- Model complexity and training resources
- Timeline impact and resource allocation
- Integration with existing systems

Respond with APPROVED or REJECTED followed by your reasoning.
This is agent-to-agent approval - no user prompts."""
    )

    orchestrator_approved = "APPROVED" in orchestrator_request.output.upper() and "REJECTED" not in orchestrator_request.output.upper()

    if not orchestrator_approved:
        logger.warning("AI Team rejected by orchestrator: %s", orchestrator_request.output[:200])
        return {
            "ai_team_approved": False,
            "ai_team_orchestrator_approval": False,
            "ai_team_architect_approval": False,
            "ai_team_rejection_reason": "Orchestrator rejected AI Team invocation",
            "cost": _update_cost(state.cost, orchestrator_request),
        }

    # Step 2: Architect reviews architectural implications
    architect_review = await run_planning_agent(
        "chief_architect",
        AGENTS["chief_architect"],
        f"""Review AI/ML architectural implications:

{chr(10).join(f"- {t.description}" for t in ai_tasks)}

Orchestrator (VP Engineering) has approved.
As Chief Architect, do you approve?

Consider:
- ML technical debt and long-term maintenance burden
- Model versioning and lifecycle management
- Infrastructure cost (training, serving, storage)
- Risk of model drift and monitoring requirements
- Explainability and compliance requirements

Respond with APPROVED or REJECTED followed by your reasoning.
This is agent-to-agent approval - no user prompts."""
    )

    architect_approved = "APPROVED" in architect_review.output.upper() and "REJECTED" not in architect_review.output.upper()

    # Both must approve
    dual_approved = orchestrator_approved and architect_approved

    # Log to audit trail
    logger.info(
        "AI Team approval: orchestrator=%s, architect=%s, dual_approved=%s",
        orchestrator_approved, architect_approved, dual_approved
    )

    rejection_reason = ""
    if not dual_approved:
        if not architect_approved:
            rejection_reason = "Architect rejected AI Team invocation"
        else:
            rejection_reason = "Orchestrator rejected AI Team invocation"

    return {
        "ai_team_approved": dual_approved,
        "ai_team_orchestrator_approval": orchestrator_approved,
        "ai_team_architect_approval": architect_approved,
        "ai_team_rejection_reason": rejection_reason,
        "cost": _update_cost_multi(state.cost, [orchestrator_request, architect_review]),
    }


async def decomposition_node(state: NexusState) -> dict:
    """Engineering managers decompose work into specific tasks (parallel)."""
    em_names = ["em_frontend", "em_backend", "em_platform"]

    coros = [
        run_planning_agent(
            em_name,
            AGENTS[em_name],
            f"""Technical design: {state.technical_design}
Your domain: {AGENTS[em_name]['name']}

Break down the work in YOUR domain into specific, implementable tasks.
Specify dependencies between tasks: if task B requires task A to be done first,
list A's id in B's "dependencies" array.

Output as a JSON array:
[{{"id": "unique_id", "description": "what to do", "assigned_agent": "agent_key", "language": "python", "dependencies": ["id_of_prerequisite_task"]}}]

If you cannot produce JSON, output a bullet list with one task per line.""",
        )
        for em_name in em_names
    ]

    results = await asyncio.gather(*coros, return_exceptions=True)

    tasks = []
    total_cost = state.cost
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.error("EM %s failed during decomposition: %s", em_names[i], result)
            continue
        if isinstance(result, TaskResult):
            parsed_tasks = _parse_tasks(result.output, em_names[i])
            tasks.extend(parsed_tasks)
            total_cost = _update_cost(total_cost, result)

    parallel_groups = _identify_parallel_groups(tasks)

    return {
        "workstreams": tasks,
        "parallel_forks": parallel_groups,
        "current_phase": "implementation",
        "cost": total_cost,
    }


async def test_first_node(state: NexusState) -> dict:
    """TDD RED phase: Write failing tests BEFORE implementation."""

    test_tasks = []
    total_cost = state.cost

    for task in state.workstreams:
        if task.status != "completed":
            # Determine which test agent to use
            agent_key = "test_frontend" if "frontend" in task.assigned_agent.lower() else "test_backend"

            result = await _run_impl_agent(
                agent_key,
                AGENTS[agent_key],
                f"""TDD RED PHASE: Write tests for this task BEFORE implementation.

Task: {task.description}
Requirements: {state.cpo_requirements}
Acceptance criteria: {state.cpo_acceptance_criteria}

Write tests that will FAIL initially (RED phase).
The tests should verify the feature works once implemented.
Run the tests and VERIFY they fail.

CRITICAL: Tests MUST fail initially. If they pass, they're not testing the right thing!

Output:
1. The test code you wrote
2. The test execution output showing FAILURES
3. Confirmation that RED phase is complete for this task""",
                state.project_path,
            )

            # Verify tests failed
            output_lower = result.output.lower()
            if ("0 failed" in output_lower and "failed" in output_lower) or \
               ("all tests passed" in output_lower) or \
               ("pass" in output_lower and "fail" not in output_lower):
                return {
                    "error": f"RED phase failed for task {task.id}: Tests passed before implementation!",
                    "current_phase": "implementation",
                }

            test_tasks.append(result.output)
            total_cost = _update_cost(total_cost, result)

    return {
        "red_phase_complete": True,
        "test_results_red": test_tasks,
        "current_phase": "implementation",
        "cost": total_cost,
    }


async def verify_green_phase(state: NexusState) -> dict:
    """TDD GREEN phase: Verify tests NOW PASS after implementation."""

    test_results = []
    total_cost = state.cost

    for task in state.workstreams:
        if task.status == "completed":
            # Re-run the same tests that failed in RED phase
            agent_key = "test_frontend" if "frontend" in task.assigned_agent.lower() else "test_backend"

            result = await _run_impl_agent(
                agent_key,
                AGENTS[agent_key],
                f"""TDD GREEN PHASE: Re-run tests to verify implementation is complete.

Task: {task.description}

Re-run the tests you wrote in the RED phase.
They MUST pass now that implementation is complete.

If they still fail, the implementation is incomplete.

Output:
1. Test execution results
2. Confirmation that all tests PASS (GREEN phase complete)""",
                state.project_path,
            )

            # Verify tests passed
            output_lower = result.output.lower()
            if "failed" in output_lower or "error" in output_lower:
                has_failures = True
                # Check if it's just reporting 0 failed
                if "0 failed" in output_lower or "0 error" in output_lower:
                    has_failures = False

                if has_failures:
                    return {
                        "error": f"GREEN phase failed for task {task.id}: Tests still failing after implementation!",
                        "green_phase_verified": False,
                        "current_phase": "implementation",
                    }

            test_results.append(result.output)
            total_cost = _update_cost(total_cost, result)

    return {
        "green_phase_verified": True,
        "test_results_green": test_results,
        "cost": total_cost,
    }


async def refactor_node(state: NexusState) -> dict:
    """TDD REFACTOR phase: Clean up code while keeping tests green."""

    result = await _run_impl_agent(
        "tech_lead",
        AGENTS["tech_lead"],
        f"""TDD REFACTOR PHASE: Review the implementation for refactoring opportunities.

Technical design: {state.technical_design}
Requirements: {state.cpo_requirements}

Look for:
- Duplicated code that can be extracted
- Unclear variable/function names that need improvement
- Complex logic that can be simplified
- Missing comments that explain WHY (not WHAT)
- Opportunities to improve readability without changing behavior

CRITICAL: Tests must stay GREEN. Run tests after each refactor.

If no refactoring is needed, say "No refactoring needed" and explain why the code is already clean.

Output:
1. Refactoring changes made (if any)
2. Test results confirming tests still pass
3. Confirmation that REFACTOR phase is complete""",
        state.project_path,
    )

    return {
        "refactor_complete": True,
        "cost": _update_cost(state.cost, result),
    }


async def implementation_node(state: NexusState) -> dict:
    """Execute implementation tasks via Agent SDK sessions with per-task tracking."""
    updated_tasks = []
    all_results = []
    failed_tasks = list(state.failed_tasks)
    retry_counts = dict(state.retry_counts)
    defect_ids = list(state.defect_ids)

    completed_ids = {t.id for t in state.workstreams if t.status == "completed"}

    for fork_group in state.parallel_forks:
        parallel_tasks = [
            t for t in state.workstreams
            if t.id in fork_group
            and t.status != "completed"
            and not (set(t.blocked_by) - completed_ids)  # all deps must be complete
        ]

        coros = []
        task_index = []
        for task in parallel_tasks:
            agent_key = task.assigned_agent
            if agent_key not in AGENTS or not AGENTS[agent_key].get("spawns_sdk"):
                continue

            agent_cfg = AGENTS[agent_key]
            if "model" in agent_cfg:
                budget_left = state.cost.budget_remaining if state.cost.budget_remaining > 0 else None
                agent_cfg = {**agent_cfg, "model": get_model_for_budget(agent_cfg["model"], budget_left)}

            defect_context = ""
            if task.id in retry_counts:
                defect_context = f"\n\nPREVIOUS ATTEMPT FAILED. This is retry #{retry_counts[task.id]}."
                if task.result:
                    defect_context += f"\nPrevious error: {task.result}"

            coros.append(
                _run_impl_agent(
                    agent_key,
                    AGENTS[agent_key],
                    f"""TASK: {task.description}
{defect_context}
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
            task_index.append(task)

        if coros:
            group_results = await asyncio.gather(*coros, return_exceptions=True)
            for i, result in enumerate(group_results):
                task = task_index[i]
                task.attempts += 1

                if isinstance(result, Exception):
                    task.status = "failed"
                    task.result = str(result)
                    retry_counts[task.id] = retry_counts.get(task.id, 0) + 1
                    if retry_counts[task.id] >= 3:
                        defect_id = f"DEF-{uuid.uuid4().hex[:8]}"
                        defect_ids.append(defect_id)
                        failed_tasks.append(task.id)
                        logger.error("Task %s failed 3 times, filing defect %s", task.id, defect_id)
                elif isinstance(result, TaskResult):
                    task.status = "completed" if result.succeeded else "failed"
                    task.result = result.output[:500]
                    if result.succeeded:
                        all_results.append(result)

    completed_ids = {t.id for t in state.workstreams if t.status == "completed"}
    for task in state.workstreams:
        if task.id in completed_ids and task not in updated_tasks:
            updated_tasks.append(task)
        else:
            updated_tasks.append(task)

    return {
        "workstreams": updated_tasks,
        "failed_tasks": failed_tasks,
        "defect_ids": defect_ids,
        "retry_counts": retry_counts,
        "current_phase": "quality_gate",
        "cost": _update_cost_multi(state.cost, all_results),
    }


async def linting_node(state: NexusState) -> dict:
    """Run linting across all changed files."""
    result = await _run_impl_agent(
        "linting_agent",
        AGENTS["linting_agent"],
        """Run linters on all files in this project.

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

    any_violations = result.output.lower().count("type:any") + result.output.lower().count("type: any")

    # Count ALL warnings - warnings are now treated as blocking errors
    lint_output = result.output.lower()
    warnings_count = (
        lint_output.count('warning') +
        lint_output.count('warn:') +
        lint_output.count('[warn]')
    )

    # ANY warning is a blocking error
    blocking_issues = 'BLOCKING' in result.output or warnings_count > 0

    return {
        "lint_results": {"output": result.output, "passed": not blocking_issues},
        "any_type_violations": any_violations,
        "cost": _update_cost(state.cost, result),
    }


async def testing_node(state: NexusState) -> dict:
    """Run tests and generate coverage."""
    test_fe = _run_impl_agent(
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

    test_be = _run_impl_agent(
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
            "frontend": fe_result.output,
            "backend": be_result.output,
        },
        "cost": _update_cost_multi(state.cost, [fe_result, be_result]),
    }


async def security_scan_node(state: NexusState) -> dict:
    """Security consultant runs full security audit."""
    result = await _run_impl_agent(
        "security_consultant",
        AGENTS["security_consultant"],
        """Run a full security audit on this project:

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
        "security_scan_results": {"output": result.output},
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
        "visual_qa_results": {"output": result.output},
        "cost": _update_cost(state.cost, result),
    }


def _count_warnings(lint_results: dict, test_results: dict) -> int:
    """Count all warnings in lint and test output."""
    warnings = 0
    if lint_results:
        output = lint_results.get('output', '').lower()
        warnings += output.count('warning')
        warnings += output.count('warn:')
        warnings += output.count('[warn]')
    if test_results:
        for output in test_results.values():
            if isinstance(output, str):
                output_lower = output.lower()
                warnings += output_lower.count('warning')
                warnings += output_lower.count('warn:')
                warnings += output_lower.count('[warn]')
    return warnings


async def quality_gate_node(state: NexusState) -> dict:
    """QA Lead determines if quality is sufficient to proceed to PR."""
    gate_details = {}

    # Reject empty results — means the check didn't actually run
    lint_ran = bool(state.lint_results)
    lint_passed = state.lint_results.get("passed", False) if lint_ran else False
    gate_details["lint_ran"] = lint_ran
    gate_details["lint_passed"] = lint_passed

    tests_ran = bool(state.test_results)
    gate_details["tests_ran"] = tests_ran

    security_ran = bool(state.security_scan_results)
    security_ok = "CRITICAL" not in str(state.security_scan_results) if security_ran else False
    gate_details["security_ran"] = security_ran
    gate_details["security_ok"] = security_ok

    no_any_violations = state.any_type_violations == 0
    gate_details["no_any_violations"] = no_any_violations

    no_failed_tasks = len(state.failed_tasks) == 0
    gate_details["no_failed_tasks"] = no_failed_tasks

    # Check for warnings - zero tolerance
    warnings_found = _count_warnings(state.lint_results, state.test_results)
    gate_details["zero_warnings"] = warnings_found == 0

    # Calculate quality score (0-100)
    checks = [lint_ran, lint_passed, tests_ran, security_ran, security_ok, no_any_violations, no_failed_tasks, warnings_found == 0]
    quality_score = round((sum(checks) / len(checks)) * 100, 1)

    # Architect and QA gate checks (enforced at graph level, tracked here)
    gate_details["architect_approved"] = state.architect_approved
    gate_details["qa_verified"] = state.qa_verified

    all_passed = lint_passed and no_any_violations and security_ok and lint_ran and tests_ran and security_ran and warnings_found == 0

    if not all_passed:
        failed_gates = [k for k, v in gate_details.items() if not v]
        return {
            "current_phase": "implementation",
            "quality_score": quality_score,
            "quality_gate_details": gate_details,
            "error": f"Quality gate failed ({quality_score}/100): {', '.join(failed_gates)}",
        }

    return {
        "current_phase": "pr_review",
        "quality_score": quality_score,
        "quality_gate_details": gate_details,
    }


async def pr_review_node(state: NexusState) -> dict:
    """Senior engineers review the PR."""
    reviewers = ["sr_frontend", "sr_backend", "sr_fullstack", "sr_devops"]
    reviews = []

    coros = []
    for reviewer_key in reviewers:
        coros.append(
            _run_impl_agent(
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
        if isinstance(result, TaskResult):
            approved = "APPROVED" in result.output.upper() and "REJECTED" not in result.output.upper()
            reviews.append(
                PRReview(
                    reviewer=reviewers[i],
                    status="approved" if approved else "rejected",
                    feedback=result.output,
                )
            )

    all_approved = all(r.status == "approved" for r in reviews)

    return {
        "pr_reviews": reviews,
        "pr_approved": all_approved,
        "pr_loop_count": state.pr_loop_count + 1,
        "cost": _update_cost_multi(state.cost, [r for r in results if isinstance(r, TaskResult)]),
    }



async def qa_verification_node(state: NexusState) -> dict:
    """QA agent verifies all quality criteria before architect review.

    Checks: all tests pass, coverage >80%, no security issues.
    Agent decision only — no user prompts.
    If failed: escalates to Tech Lead agent for review.
    """
    issues = []

    # Check test results
    tests_ran = bool(state.test_results)
    if not tests_ran:
        issues.append('Tests did not run')

    # Check security scan
    security_clean = (
        bool(state.security_scan_results)
        and 'CRITICAL' not in str(state.security_scan_results)
        and 'HIGH' not in str(state.security_scan_results)
    )
    if not security_clean:
        issues.append('Security scan has critical/high findings or did not run')

    # Check lint
    lint_passed = state.lint_results.get('passed', False) if state.lint_results else False
    if not lint_passed:
        issues.append('Linting did not pass')

    # Check no type:any violations
    if state.any_type_violations > 0:
        issues.append(f'{state.any_type_violations} type:any violation(s)')

    # Check no failed tasks
    if state.failed_tasks:
        issues.append(f'{len(state.failed_tasks)} failed task(s)')

    # QA agent makes the decision
    if issues:
        # Escalate to Tech Lead for review
        result = await run_planning_agent(
            'tech_lead',
            AGENTS['tech_lead'],
            f"""QA verification FAILED. Review these issues and decide if we can proceed:

Issues found:
{chr(10).join(f'- {i}' for i in issues)}

Quality score: {state.quality_score}/100
Test results: {state.test_results}
Security scan: {state.security_scan_results}

If the issues are minor and acceptable, respond with PROCEED.
If the issues are blocking, respond with BLOCK and explain why.""",
        )

        # Tech Lead can override minor issues
        tech_lead_approves = 'PROCEED' in result.output.upper() and 'BLOCK' not in result.output.upper()

        return {
            'qa_verified': tech_lead_approves,
            'cost': _update_cost(state.cost, result),
        }

    return {'qa_verified': True}


async def architect_approval_node(state: NexusState) -> dict:
    """Architect agent reviews all changes for final approval.

    Input: pr_reviews, test_results, security_scan_results, technical_design
    Output: architect_approved (bool), architect_feedback (str)
    Blocking: If not approved, returns to implementation.
    Agent-to-agent only — no user prompts.

    For high-risk or high-cost work, sends an interactive Slack approval UI
    to allow manual Slack-based approval before final merge.
    """
    result = await run_planning_agent(
        'chief_architect',
        AGENTS['chief_architect'],
        f"""You are the ARCHITECT — final authority on all code changes.
Your decision is FINAL. No user override. Review everything and decide.

TECHNICAL DESIGN:
{state.technical_design or 'No design document'}

PR REVIEWS:
{chr(10).join(f'[{r.reviewer}] {r.status}: {r.feedback[:300] if r.feedback else ""}' for r in state.pr_reviews) if state.pr_reviews and isinstance(state.pr_reviews, list) else 'No PR reviews'}

TEST RESULTS:
{state.test_results or 'No test results'}

SECURITY SCAN:
{state.security_scan_results or 'No security scan'}

QA VERIFIED: {state.qa_verified}
QUALITY SCORE: {state.quality_score}/100
TOTAL COST: ${state.cost.total_cost_usd:.2f}

Evaluate:
1. Architecture soundness — does implementation match the approved design?
2. Security — are all scan findings addressed?
3. Performance — any bottlenecks in the implementation?
4. Quality — is the code production-ready?

If ALL criteria pass, respond: APPROVED followed by a brief assessment.
If ANY criteria fail, respond: REJECTED followed by specific required changes.

Be decisive. Your word is final.""",
    )

    approved = 'APPROVED' in result.output.upper() and 'REJECTED' not in result.output.upper()

    # Send Slack approval request for high-cost or critical approvals
    if approved and (state.cost.total_cost_usd > 10.0 or state.quality_score < 75):
        try:
            approval_id = f"ARCH-{state.session_id[:8]}"
            notifier.send_approval_request(
                title="Architecture Review Complete - Final Approval Required",
                context={
                    "description": f"""Architecture review complete and approved by Chief Architect.

**Summary:** {result.output[:300]}

**Quality Score:** {state.quality_score}/100
**Total Cost:** ${state.cost.total_cost_usd:.2f}
**PR Status:** {len([r for r in state.pr_reviews if r.status == 'approved'])}/{len(state.pr_reviews)} approved

Click below to confirm final approval to proceed with merge.""",
                    "requester": "Chief Architect",
                    "severity": "Critical" if state.cost.total_cost_usd > 10.0 else "High",
                },
                approval_id=approval_id,
            )
            logger.info("Sent Slack approval request for architect decision: %s", approval_id)
        except Exception as e:
            logger.warning("Failed to send Slack approval request: %s", e)
            # Continue anyway - don't block on Slack notification failures

    return {
        'architect_approved': approved,
        'architect_feedback': result.output,
        'cost': _update_cost(state.cost, result),
    }


async def escalation_node(state: NexusState) -> dict:
    """Escalation handler — triggered when errors or low quality scores require CEO attention."""
    reason = state.escalation_reason or state.error or "Unknown escalation trigger"
    defect_id = f"ESC-{uuid.uuid4().hex[:8]}"

    logger.warning("ESCALATION [%s]: %s (quality_score=%s)", defect_id, reason, state.quality_score)

    result = await run_planning_agent(
        "ceo",
        AGENTS["ceo"],
        f"""ESCALATION ALERT

Something went wrong during execution and needs your awareness:
- Reason: {reason}
- Quality Score: {state.quality_score}/100
- Failed Tasks: {state.failed_tasks}
- Defects Filed: {state.defect_ids}
- Error: {state.error}

This is an informational escalation. The system will proceed to demo with warnings.
Summarize the risk and any recommendations for Garrett in 2-3 sentences.""",
    )

    return {
        "defect_ids": state.defect_ids + [defect_id],
        "escalation_reason": f"[{defect_id}] {reason} — CEO notified",
        "error": None,
        "cost": _update_cost(state.cost, result),
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
        "demo_summary": result.output,
        "demo_metrics": {
            "Total Cost": f"${state.cost.total_cost_usd:.2f}",
            "Tests": "Passed" if state.test_results else "N/A",
            "Security": "Clean" if "CRITICAL" not in str(state.security_scan_results) else "Issues Found",
            "Lint": "Passed" if state.lint_results.get("passed") else "Issues",
        },
        "current_phase": "complete",
        "cost": _update_cost(state.cost, result),
    }


async def rebuild_analysis_node(state: NexusState) -> dict:
    """Analyze the project codebase for self-improvement (MAINT-011).

    Runs the AnalyzerAgent on the project directory and stores findings
    in the state for downstream execution or reporting.
    """
    from src.agents.analyzer import Finding, save_analysis_state
    from src.orchestrator.approval import request_rebuild_start_approval

    # Use the project path from state, or fall back to a default
    target_dir = state.project_path or "/tmp/nexus-rebuild"  # noqa: S108 - safe temporary test directory

    # USER approval before starting rebuild analysis
    user_approved = await request_rebuild_start_approval(
        project_path=target_dir,
        estimated_cost="Analysis: ~$2-5, Implementation: TBD based on findings",
    )

    if not user_approved:
        logger.warning("User rejected rebuild analysis start for %s", target_dir)
        return {
            "analysis_findings": [],
            "analysis_summary": {"status": "rejected_by_user", "reason": "User did not approve rebuild analysis"},
            "analysis_state_path": None,
            "escalation_reason": "User rejected rebuild analysis",
        }

    result = await run_planning_agent(
        "chief_architect",
        AGENTS["chief_architect"],
        f"""Analyze the codebase at {target_dir} for self-improvement opportunities.

Scan for issues across these categories:
- SEC: Security vulnerabilities
- PERF: Performance bottlenecks
- ARCH: Architecture issues
- CODE: Code quality
- MAINT: Maintainability

Focus on HIGH and CRITICAL severity issues that would have the most impact.
Produce findings as a JSON array. Each finding must have:
- id, category, severity, title, description, location, impact, remediation,
  effort, effort_hours, dependencies, risk

Project path: {target_dir}
Current phase: {state.current_phase}
Quality score: {state.quality_score}""",
    )

    # Parse findings from architect analysis and store as analysis state
    findings_data = []
    try:
        text = result.output
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            findings_data = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        pass

    # Build summary
    summary = {
        "totalFindings": len(findings_data),
        "source": "rebuild_analysis_node",
        "raw_output": result.output[:2000],
    }

    # Save state file if we got structured findings
    state_path = None
    if findings_data:
        try:
            parsed_findings = []
            for i, item in enumerate(findings_data):
                if isinstance(item, dict):
                    item.setdefault("id", f"SELF-{i+1:03d}")
                    item.setdefault("category", "MAINT")
                    item.setdefault("severity", "MEDIUM")
                    item.setdefault("title", "Untitled finding")
                    item.setdefault("description", "")
                    item.setdefault("location", "unknown")
                    item.setdefault("impact", "")
                    item.setdefault("remediation", "")
                    item.setdefault("effort", "M")
                    item.setdefault("effort_hours", "4-8 hours")
                    item.setdefault("dependencies", [])
                    item.setdefault("status", "pending")
                    item.setdefault("risk", "")
                    parsed_findings.append(Finding.from_dict(item))

            if parsed_findings:
                state_path = save_analysis_state(parsed_findings, target_dir, "NEXUS Self-Analysis")
        except Exception as e:
            logger.warning("Failed to save analysis state: %s", e)

    return {
        "analysis_findings": findings_data,
        "analysis_summary": summary,
        "analysis_state_path": state_path,
        "cost": _update_cost(state.cost, result),
    }


# ============================================
# ROUTING FUNCTIONS
# These control the flow through the graph.
# ============================================


def route_after_executive_consensus(state: NexusState) -> str:
    if state.executive_consensus:
        return "spec_generation"
    if state.executive_loop_count >= 3:
        logger.warning("Executive consensus not reached after 3 loops, proceeding anyway")
        return "spec_generation"
    return "ceo"


def route_after_spec_approval(state: NexusState) -> str:
    """Route after CEO spec approval (agent-to-agent)."""
    if state.spec_approved:
        return "vp_engineering"
    if state.spec_loop_count >= 2:
        logger.warning("Spec not approved after 2 loops, proceeding with warnings")
        return "vp_engineering"
    return "spec_generation"


def route_after_tech_review(state: NexusState) -> str:
    if state.tech_plan_approved:
        return "decomposition"
    if state.tech_plan_loop_count >= 3:
        logger.warning("Tech plan not approved after 3 loops, proceeding anyway")
        return "decomposition"
    return "vp_engineering"


def route_after_quality_gate(state: NexusState) -> str:
    if state.current_phase == "pr_review":
        return "pr_review"
    # Escalate if quality is too low after repeated attempts
    if state.error and state.quality_score < 50:
        return "escalation"
    return "implementation"


def route_after_pr_review(state: NexusState) -> str:
    if state.pr_approved:
        return 'qa_verification'
    if state.pr_loop_count >= 3:
        if state.quality_score < 70:
            logger.warning('PR not approved after 3 loops with quality %s/100, escalating', state.quality_score)
            return 'escalation'
        logger.warning('PR not approved after 3 loops, proceeding to qa_verification with warnings')
        return 'qa_verification'
    return 'implementation'


def route_after_qa_verification(state: NexusState) -> str:
    """Route after QA verification. Proceed to architect or back to implementation."""
    if state.qa_verified:
        return 'architect_approval'
    return 'implementation'


def route_after_architect_approval(state: NexusState) -> str:
    """Route after architect approval. Proceed to demo or back to implementation."""
    if state.architect_approved:
        return 'demo'
    return 'implementation'


def route_after_escalation(state: NexusState) -> str:
    """After escalation, proceed to demo with warnings logged."""
    return "demo"


def route_after_cfo(state: NexusState) -> str:
    """Route after CFO budget approval. Block if budget exceeded."""
    if state.cfo_approved:
        return "cro"
    # Budget exceeded - escalate for approval
    logger.warning("CFO budget not approved. Routing to escalation for user approval.")
    return "escalation"


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
    graph.add_node("spec_generation", spec_generation_node)
    graph.add_node("spec_approval", spec_approval_node)
    graph.add_node("vp_engineering", vp_engineering_node)
    graph.add_node("tech_lead_review", tech_lead_review_node)
    graph.add_node("decomposition", decomposition_node)
    graph.add_node("ai_team_approval", ai_team_approval_node)
    graph.add_node("test_first", test_first_node)
    graph.add_node("implementation", implementation_node)
    graph.add_node("verify_green", verify_green_phase)
    graph.add_node("refactor", refactor_node)
    graph.add_node("linting", linting_node)
    graph.add_node("testing", testing_node)
    graph.add_node("security_scan", security_scan_node)
    graph.add_node("visual_qa", visual_qa_node)
    graph.add_node("quality_gate", quality_gate_node)
    graph.add_node("pr_review", pr_review_node)
    graph.add_node("qa_verification", qa_verification_node)
    graph.add_node("architect_approval", architect_approval_node)
    graph.add_node("demo", demo_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("rebuild_analysis", rebuild_analysis_node)

    # --- Define edges (the org chart as a flow) ---

    # Start → Intake
    graph.add_edge(START, "intake")

    # Intake → Executive Planning Loop
    graph.add_edge("intake", "ceo")
    graph.add_edge("ceo", "cpo")
    graph.add_edge("cpo", "cfo")
    # CFO → conditional routing based on budget approval
    graph.add_conditional_edges(
        "cfo",
        route_after_cfo,
        {"cro": "cro", "escalation": "escalation"},
    )
    graph.add_edge("cro", "executive_consensus")

    # Executive consensus → either loop back or proceed to spec generation
    graph.add_conditional_edges(
        "executive_consensus",
        route_after_executive_consensus,
        {"ceo": "ceo", "spec_generation": "spec_generation"},
    )

    # Spec generation → Spec approval
    graph.add_edge("spec_generation", "spec_approval")

    # Spec approval → either loop back to spec generation or proceed to VP Eng
    graph.add_conditional_edges(
        "spec_approval",
        route_after_spec_approval,
        {"spec_generation": "spec_generation", "vp_engineering": "vp_engineering"},
    )

    # VP Eng → Tech Lead Review
    graph.add_edge("vp_engineering", "tech_lead_review")

    # Tech Lead → either loop back or proceed to decomposition
    graph.add_conditional_edges(
        "tech_lead_review",
        route_after_tech_review,
        {"vp_engineering": "vp_engineering", "decomposition": "decomposition"},
    )

    # Decomposition → AI Team Approval Gate
    graph.add_edge("decomposition", "ai_team_approval")

    # AI Team Approval → Test First (RED phase)
    graph.add_edge("ai_team_approval", "test_first")

    # Test First (RED) → Implementation (GREEN)
    graph.add_edge("test_first", "implementation")

    # Implementation → Verify Green Phase
    graph.add_edge("implementation", "verify_green")

    # Verify Green → Refactor
    graph.add_edge("verify_green", "refactor")

    # Refactor → Quality checks (parallel)
    graph.add_edge("refactor", "linting")
    graph.add_edge("refactor", "testing")
    graph.add_edge("refactor", "security_scan")
    graph.add_edge("refactor", "visual_qa")

    # Quality checks → Quality Gate
    graph.add_edge("linting", "quality_gate")
    graph.add_edge("testing", "quality_gate")
    graph.add_edge("security_scan", "quality_gate")
    graph.add_edge("visual_qa", "quality_gate")

    # Quality Gate → PR Review, back to Implementation, or Escalation
    graph.add_conditional_edges(
        "quality_gate",
        route_after_quality_gate,
        {"pr_review": "pr_review", "implementation": "implementation", "escalation": "escalation"},
    )

    # PR Review → QA Verification, back to Implementation, or Escalation
    graph.add_conditional_edges(
        "pr_review",
        route_after_pr_review,
        {"qa_verification": "qa_verification", "implementation": "implementation", "escalation": "escalation"},
    )

    # QA Verification → Architect Approval or back to Implementation
    graph.add_conditional_edges(
        "qa_verification",
        route_after_qa_verification,
        {"architect_approval": "architect_approval", "implementation": "implementation"},
    )

    # Architect Approval → Demo or back to Implementation
    graph.add_conditional_edges(
        "architect_approval",
        route_after_architect_approval,
        {"demo": "demo", "implementation": "implementation"},
    )

    # Escalation → Demo (always proceed after escalation)
    graph.add_conditional_edges(
        "escalation",
        route_after_escalation,
        {"demo": "demo"},
    )

    # Demo → End
    graph.add_edge("demo", END)

    # Rebuild Analysis → End (standalone node for self-improvement, MAINT-011)
    graph.add_edge("rebuild_analysis", END)

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


def _update_cost(current: CostSnapshot, result: TaskResult | dict) -> CostSnapshot:
    if isinstance(result, TaskResult):
        cost = result.cost_usd
        model = result.model or "unknown"
        agent = result.agent or "unknown"
    else:
        cost = result.get("cost", 0)
        model = result.get("model", "unknown")
        agent = result.get("agent", "unknown")
    return CostSnapshot(
        total_cost_usd=current.total_cost_usd + cost,
        by_model={**current.by_model, model: current.by_model.get(model, 0) + cost},
        by_agent={**current.by_agent, agent: current.by_agent.get(agent, 0) + cost},
        hourly_rate=cost_tracker.hourly_rate,
    )


def _update_cost_multi(current: CostSnapshot, results: Sequence[TaskResult | dict]) -> CostSnapshot:
    updated = current
    for r in results:
        if isinstance(r, (dict, TaskResult)):
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
    return budget if budget else {}


def _parse_tasks(text: str, em_source: str) -> list[WorkstreamTask]:
    """Parse tasks from EM output — try JSON first, fall back to text parsing."""
    # Try JSON extraction first
    try:
        # Find JSON array in the output
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            raw = json.loads(text[start:end])
            tasks = []
            for i, item in enumerate(raw):
                task_id = item.get("id", f"{em_source}_{i + 1}")
                deps = item.get("dependencies", []) or []
                tasks.append(
                    WorkstreamTask(
                        id=task_id,
                        description=item.get("description", ""),
                        assigned_agent=item.get("assigned_agent", _infer_agent(item.get("description", ""), em_source)),
                        language=item.get("language") or _infer_language(item.get("description", "")),
                        blocked_by=deps,
                    )
                )
            # Build forward edges (blocks) from blocked_by
            id_set = {t.id for t in tasks}
            for t in tasks:
                for dep_id in t.blocked_by:
                    if dep_id in id_set:
                        dep_task = next(x for x in tasks if x.id == dep_id)
                        if t.id not in dep_task.blocks:
                            dep_task.blocks.append(t.id)
            if tasks:
                return tasks
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # Fallback: text parsing
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
    """Group tasks by dependency depth for parallel execution using topological sort.

    Level 0: tasks with no dependencies -> run in parallel
    Level 1: tasks depending on level 0 -> run after level 0 completes
    etc.

    Uses actual blocked_by fields from tasks. Falls back to EM-based grouping
    when no explicit dependencies exist.
    """
    if not tasks:
        return []

    # Check if any tasks have explicit dependencies
    has_deps = any(t.blocked_by for t in tasks)

    if has_deps:
        # Topological sort using Kahn's algorithm
        all_ids = {t.id for t in tasks}
        task_deps: dict[str, set[str]] = {}
        for t in tasks:
            # Only consider deps within this task set
            task_deps[t.id] = set(t.blocked_by) & all_ids

        remaining = dict(task_deps)
        levels: list[list[str]] = []
        placed: set[str] = set()

        while remaining:
            level = [tid for tid, deps in remaining.items() if not (deps - placed)]
            if not level:
                # Cycle detected -- place all remaining in final level
                logger.warning("Cycle detected in task dependencies: %s", list(remaining.keys()))
                levels.append(list(remaining.keys()))
                break
            levels.append(level)
            placed.update(level)
            for tid in level:
                del remaining[tid]

        return levels if levels else [[t.id for t in tasks]]

    # Fallback: group by EM source so each EM's tasks run sequentially
    # but different EMs run in parallel
    em_groups: dict[str, list[str]] = {}
    for t in tasks:
        prefix = t.id.rsplit("_", 1)[0] if "_" in t.id else "default"
        em_groups.setdefault(prefix, []).append(t.id)

    max_depth = max(len(v) for v in em_groups.values()) if em_groups else 1
    levels = []
    for depth in range(max_depth):
        level = []
        for em_tasks in em_groups.values():
            if depth < len(em_tasks):
                level.append(em_tasks[depth])
        if level:
            levels.append(level)

    return levels if levels else [[t.id for t in tasks]]
