# ADR-001: Consolidate to LangGraph-Only Orchestration

**Status:** Accepted
**Date:** 2026-02-14
**Author:** ARCH-001 implementation

## Context

NEXUS had two complete orchestration systems coexisting:

1. **ReasoningEngine** (`src/orchestrator/engine.py`) — A tick-based polling loop
   that dispatched engineers, ran QA cycles, managed cooldowns, and polled for
   events every 6 seconds. Used `memory.db` for state.

2. **LangGraph Orchestrator** (`src/orchestrator/graph.py`) — A DAG-based graph
   with Pydantic state (`NexusState`), checkpointing via `MemorySaver`, and
   structured flow through executive planning, implementation, quality gates,
   PR review, and demo nodes.

3. **Executor** (`src/orchestrator/executor.py`) — A lightweight fast-path that
   bypasses the full graph for simple directives.

The dual systems caused confusion about which path a directive would take,
duplicated logic for task dispatch, QA, and code review, and created maintenance
burden when changes needed to be reflected in both paths.

## Decision

Consolidate to **LangGraph as the primary orchestration path**:

- **Keep** `graph.py` (LangGraph) as the single directive execution pipeline
- **Keep** `executor.py` as an explicit fast-path toggle for simple directives
- **Retire** the ReasoningEngine's tick loop, `_dispatch_engineers`, `_run_qa`,
  `_run_code_review`, cooldown management, and all polling-based dispatch logic
- **Retain** useful utilities from engine.py: `understand()` (NLU), `fast_decompose()`,
  `notify_slack()`, and the `handle_message()` facade

## Implementation

`engine.py` was rewritten as `OrchestrationFacade` — a thin adapter that:

1. Keeps the same public API (`engine.start()`, `engine.stop()`, `engine.handle_message()`)
2. Classifies messages via `understand()` (Haiku NLU) — unchanged
3. Routes directives to LangGraph via `compile_nexus_dynamic()` + `ainvoke()`
4. Handles conversational intents (status, chat, feedback, stop) inline
5. Manages active LangGraph tasks with proper cancellation on stop/pivot

All callers (`server.py`, `daemon/server.py`, `test_server_auth.py`) continue to
import `from src.orchestrator.engine import engine` with no changes needed.

## What Was Removed

- `ReasoningEngine` class and its tick-based `_loop()` / `_tick()` cycle
- `_dispatch_engineers()` — agent matching, cooldown tracking, ML routing
- `_run_pms()`, `_run_qa()`, `_run_code_review()` — role-based dispatch
- `_check_build_done()`, `_check_qa_done()`, `_check_fixes_done()` — polling checks
- `_run_plugin_review()`, `_check_plugin_review_done()` — plugin review with TTL cache
- `_safe_run()` — circuit breaker + escalation wrapper (now handled by graph nodes)
- `_match()` — engineer-to-task matching with ML + keyword fallback
- Hire/fire handlers (org mutations now handled by `daemon/server.py` via Haiku intake)
- Plugin review result cache (`_plugin_review_results`, TTL/LRU logic)
- All cooldown dictionaries and QA cycle counters

## Consequences

**Positive:**
- Single orchestration path reduces confusion and maintenance burden
- LangGraph provides structured state, checkpointing, and DAG-based flow
- Quality gates, PR review, and escalation are explicit graph nodes
- Parallel execution of quality checks (lint, test, security, visual QA) is native

**Negative:**
- Circuit breaker + escalation logic from `_safe_run()` is not yet ported to
  individual graph nodes (tracked as follow-up)
- Hire/fire via `handle_message()` is removed — org mutations go through
  `daemon/server.py` Haiku intake path instead

**Neutral:**
- The `executor.py` fast-path remains unchanged and available via explicit toggle
- `daemon/server.py` already used LangGraph — no changes needed there
- Slack listener (`listener.py`) never used the engine directly — no changes needed
