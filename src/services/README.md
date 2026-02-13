# SSoT Services — Single Source of Truth Layer

Unified typed access to NEXUS data spread across multiple databases.

## Problem

Agent data exists in multiple databases:
- `registry.db` — agent config, org structure, circuit events
- `ml.db` — performance metrics, embeddings, training data
- `cost.db` — spend tracking
- `memory.db` — directives, tasks, world state
- `kpi.db` — business metrics

Different code paths (orchestrator, ML pipeline, API endpoints, status queries) each access these databases directly with no shared contract.

## Solution

Service layer provides typed composite views that hide the multi-database reality.

## Services

### AgentService (`agent_service.py`)

Composite view of agents across config, performance, and cost data.

```python
from src.services.agent_service import agent_service

# Get single agent profile
profile = agent_service.get_agent_profile("sr_backend")
print(f"{profile.name}: {profile.success_rate:.1%} success, ${profile.avg_cost:.4f}/task")

# List all active agents with stats
profiles = agent_service.list_agent_profiles()
```

**AgentProfile fields:**
- Config: `agent_id`, `name`, `model`, `layer`, `status`, `tools`
- Performance: `success_rate`, `avg_cost`, `avg_defects`, `total_tasks`
- Circuit state: `circuit_trips`, `recoveries`

### DirectiveService (`directive_service.py`)

Directive lifecycle with related tasks.

```python
from src.services.directive_service import directive_service

# Get directive with tasks
status = directive_service.get_directive(directive_id)
print(f"{status.text}: {len(status.tasks)} tasks")

# List active directives
active = directive_service.list_active_directives()
```

**DirectiveStatus fields:**
- `directive_id`, `text`, `status`, `intent`, `project_path`
- `tasks` — list of task_board entries
- `created_at`, `updated_at`

### OutcomeService (`outcome_service.py`)

Task outcomes and ML training data.

```python
from src.services.outcome_service import outcome_service

summary = outcome_service.get_summary()
print(f"Success rate: {summary.success_rate:.1%}")
print(f"Avg cost: ${summary.avg_cost:.4f}")
```

**OutcomeSummary fields:**
- `total_outcomes`, `success_rate`, `avg_cost`, `avg_defects`
- `training_data_count` — ML store record count

### KnowledgeService (`knowledge_service.py`)

RAG knowledge base status and retrieval.

```python
from src.services.knowledge_service import knowledge_service

# Check status
status = knowledge_service.get_status()
print(f"{status.total_chunks} chunks, ready={status.ready}")

# Get context for a query
context = knowledge_service.get_context("How do I debug build errors?")
```

**KnowledgeStatus fields:**
- `total_chunks`, `chunks_by_type`, `ready`

## Usage Pattern

1. Import the singleton service instance
2. Call typed methods
3. Get dataclass responses (never raw dicts)

```python
from src.services.agent_service import agent_service

profile = agent_service.get_agent_profile("ceo")
if profile:
    print(f"{profile.name} has {profile.total_tasks} tasks")
```

## Benefits

- **Single source of truth** — one API for multi-database queries
- **Type safety** — dataclasses catch field errors at development time
- **Isolation** — changes to underlying schemas don't break consumers
- **Testability** — easy to mock service layer for tests
- **Performance** — services can cache, batch, or optimize queries

## Migration Path

Existing code that directly queries `registry`, `ml_store`, `cost_tracker`, or `memory` can gradually migrate to services. Both patterns work during transition.
