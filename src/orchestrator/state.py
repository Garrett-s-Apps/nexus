"""
NEXUS State Schema

This defines the typed state that flows through the LangGraph graph.
Every node reads from and writes to this state. This is how agents
communicate without talking to each other directly.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkstreamTask(BaseModel):
    id: str
    description: str
    assigned_agent: str
    language: str | None = None
    files: list[str] = Field(default_factory=list)
    status: Literal["pending", "in_progress", "completed", "failed", "blocked"] = "pending"
    result: str | None = None
    token_cost: float = 0.0
    attempts: int = 0


class PRReview(BaseModel):
    reviewer: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    feedback: str | None = None
    rejection_reasons: list[str] = Field(default_factory=list)


class CostSnapshot(BaseModel):
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_usd: float = 0.0
    hourly_rate: float = 0.0
    budget_remaining: float = 0.0
    by_model: dict[str, float] = Field(default_factory=dict)
    by_agent: dict[str, float] = Field(default_factory=dict)


class NexusState(BaseModel):
    """The complete state that flows through the NEXUS LangGraph graph."""

    # --- Input ---
    directive: str = ""
    source: Literal["slack", "ide", "cli", "api"] = "slack"
    session_id: str = ""
    project_path: str = ""

    # --- Executive Planning ---
    strategic_brief: str | None = None
    ceo_approved: bool = False
    cpo_requirements: str | None = None
    cpo_acceptance_criteria: list[str] = Field(default_factory=list)
    cfo_budget_allocation: dict[str, float] = Field(default_factory=dict)
    cfo_approved: bool = False
    cro_timeline: str | None = None
    cro_approved: bool = False
    executive_consensus: bool = False
    executive_loop_count: int = 0

    # --- Technical Planning ---
    technical_design: str | None = None
    architecture_decisions: list[str] = Field(default_factory=list)
    component_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    api_contracts: list[dict[str, Any]] = Field(default_factory=list)
    tech_plan_approved: bool = False
    tech_plan_loop_count: int = 0

    # --- Workstream Management ---
    workstreams: list[WorkstreamTask] = Field(default_factory=list)
    parallel_forks: list[list[str]] = Field(default_factory=list)
    merge_conflicts: list[str] = Field(default_factory=list)

    # --- Implementation ---
    files_changed: list[str] = Field(default_factory=list)
    commits: list[str] = Field(default_factory=list)
    branch_name: str | None = None

    # --- Quality ---
    lint_results: dict[str, Any] = Field(default_factory=dict)
    test_results: dict[str, Any] = Field(default_factory=dict)
    test_coverage: float = 0.0
    security_scan_results: dict[str, Any] = Field(default_factory=dict)
    visual_qa_results: dict[str, Any] = Field(default_factory=dict)
    any_type_violations: int = 0

    # --- PR Review ---
    pr_url: str | None = None
    pr_reviews: list[PRReview] = Field(default_factory=list)
    pr_approved: bool = False
    pr_loop_count: int = 0

    # --- Demo ---
    demo_summary: str | None = None
    demo_screenshots: list[str] = Field(default_factory=list)
    demo_metrics: dict[str, str] = Field(default_factory=dict)

    # --- Cost Tracking ---
    cost: CostSnapshot = Field(default_factory=CostSnapshot)

    # --- Quality Tracking (Phase 3) ---
    quality_score: float = 0.0
    failed_tasks: list[str] = Field(default_factory=list)
    defect_ids: list[str] = Field(default_factory=list)
    retry_counts: dict[str, int] = Field(default_factory=dict)
    quality_gate_details: dict[str, bool] = Field(default_factory=dict)

    # --- Flow Control ---
    current_phase: Literal[
        "intake",
        "executive_planning",
        "technical_planning",
        "decomposition",
        "implementation",
        "quality_gate",
        "pr_review",
        "demo",
        "complete",
        "escalation"
    ] = "intake"
    error: str | None = None
    escalation_reason: str | None = None

    # --- Messages (for LangGraph compatibility) ---
    messages: list[Any] = Field(default_factory=list)
