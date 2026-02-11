# NEXUS: Enterprise Multi-Agent Orchestration System

## Architecture Specification v1.0

---

## 1. System Philosophy

NEXUS operates as a fully autonomous software engineering organization. It does not ask the human for guidance during execution. It plans internally, debates internally, critiques internally, and only surfaces completed work for review — or escalates when a genuine blocker exists that cannot be resolved by the system itself.

**Core Principles:**

- **Autonomy First**: The system plans, executes, and iterates without human prompting. The human sets the objective; NEXUS delivers the result.
- **Cost-Aware Intelligence**: Every decision weighs quality against token cost. The system continuously optimizes its own workflows to reduce waste without sacrificing output quality.
- **Real-World Validation**: Every output is evaluated from the perspective of a real human reading, using, or interacting with it. No "AI-looking" output ships.
- **Self-Improving Collaboration**: Agents learn how they work best together and establish persistent working relationships and patterns.
- **Direct Access**: Any Sonnet or Opus agent is directly addressable by the human. That agent then coordinates with its team to implement feedback.

---

## 2. Organizational Structure

### 2.1 Executive Layer (Strategic Decision-Making)

These agents operate at the highest level of abstraction. They don't write code — they make decisions about what gets built, why, and whether it meets the bar.

| Role | Model | Responsibility |
|------|-------|----------------|
| **CEO** | Opus | Final authority on product direction. Resolves conflicts between executives. Owns the "ship or don't ship" decision. |
| **CFO** | Sonnet | Owns token budget allocation. Monitors cost-per-task, cost-per-feature. Can veto expensive approaches and demand cheaper alternatives. Tracks ROI of agent work. |
| **CPO (Chief Product Officer)** | Opus | Owns requirements fidelity. Ensures every feature matches the human's intent. Validates UX decisions. The "would a real person actually use this?" check. |
| **CRO (Chief Revenue Officer)** | Sonnet | Owns delivery velocity and throughput. Optimizes for shipping speed without quality loss. Identifies bottlenecks and reallocates resources. |

### 2.2 Consultant Layer (Specialized Advisory)

On-demand specialists invoked by executives or the orchestrator when domain expertise is needed.

| Role | Model | Provider | Specialty |
|------|-------|----------|-----------|
| **Frontend UX Consultant** | Gemini | Google | Visual reasoning, layout validation, CSS/accessibility audits. Gemini's multimodal strength catches the "white text on white background" class of bugs. |
| **Systems Architecture Consultant** | o3 | OpenAI | Complex algorithmic design, performance optimization, systems-level reasoning for C/C++/Go workloads. |
| **Security Consultant** | Opus | Anthropic | Threat modeling, auth flows, secrets management, dependency audits. |
| **DevOps Consultant** | Sonnet | Anthropic | CI/CD pipeline design, containerization, deployment strategies, infrastructure-as-code. |
| **Cost Optimization Consultant** | Haiku | Anthropic | Analyzes agent workflow patterns and recommends efficiency improvements. Reports to CFO. |

### 2.3 Engineering Management Layer

| Role | Model | Responsibility |
|------|-------|----------------|
| **VP of Engineering** | Opus | Translates executive decisions into technical strategy. Owns architecture governance. |
| **Engineering Manager — Frontend** | Sonnet | Manages frontend team. Owns UI/UX quality bar. Reviews all frontend PRs. |
| **Engineering Manager — Backend** | Sonnet | Manages backend team. Owns API design, data modeling, performance. |
| **Engineering Manager — Platform** | Sonnet | Manages DevOps, security, testing infrastructure. |
| **Tech Lead** | Opus | Deepest technical authority. Makes final call on architectural disputes. Code-level debugging escalation. |

### 2.4 Senior Engineering Layer (PR Review & Governance)

| Role | Model | Responsibility |
|------|-------|----------------|
| **Sr. Frontend Engineer** | Sonnet | Reviews frontend PRs. Enforces design system consistency. Catches CSS/layout bugs. |
| **Sr. Backend Engineer** | Sonnet | Reviews backend PRs. Validates API contracts, data integrity, error handling. |
| **Sr. Full-Stack Engineer** | Sonnet | Reviews cross-cutting PRs. Validates frontend-backend integration. |
| **Sr. DevOps Engineer** | Sonnet | Reviews infrastructure PRs. Validates deployment configs, CI pipelines. |

### 2.5 Implementation Layer

| Role | Model | Languages |
|------|-------|-----------|
| **Frontend Developer** | Sonnet | React, Next.js, HTML, CSS, HTMX, TypeScript, JavaScript |
| **Backend Developer — JVM/Systems** | Sonnet | Java, Go, C, C++, C# |
| **Backend Developer — Scripting** | Sonnet | Python, Ruby/Rails, PHP, Node.js |
| **Full-Stack Developer** | Sonnet | All of the above |
| **DevOps Engineer** | Sonnet | Docker, K8s, Terraform, GitHub Actions, CI/CD |

### 2.6 Quality Assurance Layer

| Role | Model | Responsibility |
|------|-------|----------------|
| **QA Lead** | Sonnet | Designs test strategy. Determines what needs unit, integration, and e2e tests. |
| **Test Engineer — Frontend** | Sonnet | Writes meaningful frontend tests (not boilerplate). Tests user flows, not implementation details. |
| **Test Engineer — Backend** | Sonnet | Writes backend tests. Focuses on edge cases, error paths, data integrity. |
| **Linting & Standards Agent** | Haiku | Runs linters across all supported languages. Enforces style guides. Fast, cheap, parallelizable. |

### 2.7 Haiku Swarm Layer (Parallel Execution)

Haiku agents are the workforce. They're cheap, fast, and parallelizable. They handle high-volume, well-defined tasks under supervision of Sonnet/Opus agents.

| Swarm Type | Tasks |
|------------|-------|
| **Code Writers** | Implement well-specified functions/components from detailed specs |
| **Test Writers** | Generate unit tests from specs + implementation |
| **Linters** | Run language-specific linting across files |
| **Doc Updaters** | Update documentation after each commit |
| **File Scanners** | Search codebases for patterns, dependencies, usages |
| **Formatters** | Apply consistent formatting, fix imports, organize files |
| **Migrators** | Handle repetitive refactoring tasks (rename, move, update references) |

---

## 3. Workflow Architecture

### 3.1 DAG-Based Orchestration with Auto-Forking

```
Human Input (Objective)
       │
       ▼
┌──────────────┐
│  CEO + CPO   │  Strategic Planning (What are we building? Why?)
│  + CRO + CFO │  CFO sets token budget. CRO sets timeline. CPO defines acceptance criteria.
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ VP of Eng +  │  Technical Planning (How do we build it?)
│  Tech Lead   │  Decompose into workstreams. Identify parallelizable work.
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│           ORCHESTRATOR (LangGraph)            │
│                                               │
│  - Builds execution DAG from tech plan        │
│  - Identifies independent workstreams         │
│  - AUTO-FORKS parallel branches               │
│  - Monitors cost via CFO budget allocation    │
│  - Routes to specialists by language/domain   │
└──┬────────┬────────┬────────┬────────┬───────┘
   │        │        │        │        │
   ▼        ▼        ▼        ▼        ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│ Fork │ │ Fork │ │ Fork │ │ Fork │ │ Fork │   ← Parallel Workstreams
│  1   │ │  2   │ │  3   │ │  4   │ │  5   │
└──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘
   │        │        │        │        │
   ▼        ▼        ▼        ▼        ▼
┌──────────────────────────────────────────────┐
│              MERGE + INTEGRATION              │
│  Sr. Engineers review cross-fork conflicts    │
│  Full-Stack Dev handles integration           │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│   PR CYCLE   │  (See Section 3.3)
└──────────────┘
```

### 3.2 Internal Planning Protocol ("Plan Before Execute")

This is the critical difference from current systems. No code is written until the plan is solid.

**Phase 1: Strategic Alignment** (CEO, CPO, CRO, CFO)
- CPO drafts requirements interpretation
- CEO validates alignment with objective
- CRO estimates delivery timeline
- CFO allocates token budget with hard limits per workstream
- Output: Approved Strategic Brief

**Phase 2: Technical Design** (VP Eng, Tech Lead, Consultants as needed)
- Decompose into components, services, modules
- Identify language per component
- Design API contracts and data models
- Call in consultants (Gemini for UI validation, o3 for systems design)
- Output: Technical Design Document

**Phase 3: Internal Review** (All Eng Managers + Sr. Engineers)
- Each manager reviews their domain
- Challenge assumptions, identify risks
- Vote: Ready / Needs Revision
- Must achieve unanimous "Ready" before execution begins
- Output: Approved Execution Plan

**Phase 4: Execution** (Implementation Layer + Haiku Swarm)
- Orchestrator builds DAG, forks workstreams
- Haiku swarm executes parallelizable tasks
- Sonnet agents handle complex implementation
- Continuous linting during development

**Phase 5: Quality Gate** (QA Layer + Sr. Engineers)
- Meaningful unit tests (not boilerplate)
- Integration tests for cross-component flows
- Visual validation (Gemini consultant for UI)
- Performance benchmarks

### 3.3 PR and Governance Cycle

```
Implementation Complete
       │
       ▼
┌──────────────────┐
│  Auto-Raise PR   │  DevOps agent creates PR with:
│                  │  - Change summary
│                  │  - Test results
│                  │  - Cost report (tokens used)
│                  │  - Screenshots (if UI change)
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  SR. DEV REVIEW  │  Assigned based on domain:
│  (2 reviewers)   │  - Architecture check (Tech Lead)
│                  │  - Domain check (Sr. Engineer)
│                  │  - Design check (Eng Manager)
└──────┬───────────┘
       │
       ├── APPROVED ──────► Merge + Haiku doc update
       │
       └── REJECTED ──────► Feedback loop
              │
              ▼
       ┌──────────────┐
       │ Implementing  │  Agent receives specific feedback.
       │ agent fixes   │  Does NOT escalate to human.
       │ and resubmits │  Loops until PR passes or
       └──────────────┘  CFO flags cost overrun.
```

### 3.4 Governance Gates (Rejection Criteria)

A PR is sent back if it fails ANY of:

- **Architecture**: Doesn't match approved technical design
- **Design**: UI doesn't match design specs or fails visual validation
- **Quality**: Tests are boilerplate/meaningless, or insufficient coverage
- **Performance**: Introduces regressions or doesn't meet benchmarks
- **Security**: Introduces vulnerabilities, hardcoded secrets, injection risks
- **Standards**: Fails linting, doesn't follow code style, bad naming
- **Comments**: Contains "what the code does" comments instead of "why" comments
- **Cost**: Implementation used significantly more tokens than budgeted

---

## 4. Multi-Model Strategy

### 4.1 Model Assignment Philosophy

| Model | Provider | Strengths | System Role |
|-------|----------|-----------|-------------|
| **Opus** | Anthropic | Deep reasoning, debugging strategy, nuanced judgment | CEO, CPO, Tech Lead, VP Eng, Security Consultant, debugging approach/strategy |
| **Sonnet** | Anthropic | Strong coding, good reasoning, balanced cost | Engineering Managers, Sr. Engineers, Implementation, QA Lead, code documentation |
| **Haiku** | Anthropic | Fast, cheap, good for well-defined tasks | Swarm tasks, linting, doc updates, formatting, simple implementations |
| **Gemini** | Google | Multimodal, visual reasoning, long context | Frontend UX validation, visual QA, layout auditing, accessibility |
| **o3** | OpenAI | Systems reasoning, algorithmic complexity | Systems architecture consulting, performance optimization, complex algorithm design |

### 4.2 Debugging Protocol

```
Bug Detected
     │
     ▼
┌─────────────┐
│   OPUS      │  Debugging APPROACH
│             │  - Analyzes symptoms
│             │  - Forms hypotheses
│             │  - Designs investigation plan
│             │  - Identifies root cause
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   HAIKU     │  Debugging EXECUTION
│   SWARM     │  - Runs investigation steps
│             │  - Adds logging/instrumentation
│             │  - Tests hypotheses
│             │  - Applies fix
│             │  - Verifies fix
└─────────────┘
```

### 4.3 Frontend Visual Validation (Solving the White-on-White Problem)

```
UI Implementation Complete
       │
       ▼
┌─────────────────┐
│  SCREENSHOT     │  Automated rendering of all states:
│  GENERATION     │  - Light mode, dark mode
│                 │  - All breakpoints (mobile, tablet, desktop)
│                 │  - Empty states, loading states, error states
│                 │  - With realistic data (not lorem ipsum)
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│  GEMINI         │  Visual QA:
│  CONSULTANT     │  - Contrast validation (WCAG AA minimum)
│                 │  - Layout coherence
│                 │  - Text readability
│                 │  - Interactive element visibility
│                 │  - Responsive behavior check
│                 │  - "Does this look like a real product?"
└──────┬──────────┘
       │
       ├── PASS ──────► Continue to PR
       │
       └── FAIL ──────► Specific feedback to Frontend Dev
                        with exact CSS/HTML fix recommendations
```

---

## 5. Cost Management System

### 5.1 CFO Budget Allocation

The CFO agent manages a token budget for every task. This is not advisory — it's enforced.

```
Token Budget Structure:
├── Strategic Planning:     5% of total budget
├── Technical Design:       5% of total budget
├── Implementation:         50% of total budget
│   ├── Per-workstream caps (set by CFO)
│   └── Emergency reserve: 10% of implementation budget
├── Testing:                15% of total budget
├── Review & Iteration:     15% of total budget
└── Documentation:          10% of total budget
```

### 5.2 Cost Optimization Loop

The system continuously monitors and optimizes its own efficiency:

1. **Per-Task Tracking**: Every agent call logs tokens in, tokens out, and outcome (success/failure/revision needed)
2. **Pattern Detection**: Cost Optimization Consultant (Haiku) analyzes patterns weekly:
   - Which agents produce the most revisions? Why?
   - Which task types cost more than expected?
   - Where are tokens being wasted on back-and-forth?
3. **Workflow Adjustment**: CFO + CRO implement changes:
   - Promote task types from Sonnet to Haiku if quality holds
   - Demote task types from Haiku to Sonnet if revision rate is too high
   - Adjust planning depth based on task complexity
   - Cache common patterns to avoid re-reasoning

### 5.3 Self-Optimization Rules

- If a Haiku agent fails a task 2+ times, escalate to Sonnet (don't keep burning Haiku tokens on retries)
- If a Sonnet agent's output passes review on first try 90%+ of the time for a task type, evaluate whether Haiku can handle it
- If planning phase exceeds budget, truncate and execute with best-available plan (don't gold-plate planning)
- If a review loop exceeds 3 iterations, escalate to Tech Lead for root cause (the spec might be ambiguous, not the implementation)

---

## 6. Code Quality Standards

### 6.1 Comment Philosophy

```
❌ BAD (describes what the code does):
// Loop through users and filter active ones
const activeUsers = users.filter(u => u.isActive);

❌ BAD (restates the code):
// Set timeout to 30 seconds
const TIMEOUT = 30000;

✅ GOOD (explains WHY):
// Vonage API drops connections silently after 30s of inactivity,
// so we ping slightly under that threshold
const TIMEOUT = 28000;

✅ GOOD (captures business context):
// AssetMark compliance requires PII to never touch client-side storage,
// even in encrypted form — route through server-side session only
const session = await serverSession.get(userId);

✅ BEST (no comment needed — self-documenting):
const VONAGE_SILENT_DISCONNECT_THRESHOLD_MS = 28000;
```

**Rule**: If you feel the need to comment, first try to rewrite the code so the comment is unnecessary. If a comment is still needed, it must explain WHY, never WHAT.

### 6.2 Testing Philosophy

```
❌ MEANINGLESS (tests implementation, not behavior):
test('returns true when isActive is true', () => {
  expect(isActive({ isActive: true })).toBe(true);
});

✅ MEANINGFUL (tests real scenarios):
test('expired trial accounts are treated as inactive even if manually flagged active', () => {
  const account = createTrialAccount({ expiresAt: daysAgo(1), manuallyActivated: true });
  expect(accountIsActive(account)).toBe(false);
});

✅ MEANINGFUL (tests edge cases that actually break things):
test('handles advisor names with unicode characters in Salesforce sync', () => {
  const advisor = { name: 'José María García-López' };
  const result = syncToSalesforce(advisor);
  expect(result.name).toBe('José María García-López');
});
```

**Rule**: Every test should answer: "What real-world scenario does this protect against?" If the answer is "none, it just tests that the code works as written," delete it.

### 6.3 Documentation Protocol

| Event | Agent | Action |
|-------|-------|--------|
| Feature complete | Sonnet | Writes comprehensive documentation: architecture decisions, API docs, usage examples, known limitations |
| Each commit | Haiku | Updates existing docs to reflect changes. Keeps docs in sync with code. |
| Major refactor | Sonnet | Rewrites affected documentation sections |
| Quarterly | Sonnet | Full documentation audit and refresh |

---

## 7. Human Interaction Model

### 7.1 When NEXUS Contacts the Human

NEXUS does NOT contact the human for:
- Planning decisions
- Technical choices
- Bug investigation
- Review feedback
- Resource allocation

NEXUS ONLY contacts the human for:
- **Delivery**: "Here's the completed feature. Here's what we built and why."
- **Genuine Ambiguity**: Requirements that cannot be resolved by CPO interpretation (rare)
- **Budget Escalation**: CFO has determined the task exceeds budget and needs human approval to continue
- **Critical Risk**: Security Consultant has identified a risk that requires human judgment

### 7.2 Direct Agent Access

The human can address any Sonnet or Opus agent directly:

```
Human: "@frontend-dev The navigation feels sluggish on mobile. Fix it."

Frontend Dev receives message → 
  Consults with Eng Manager Frontend →
  Runs performance audit →
  Identifies cause →
  Implements fix →
  Gets reviewed by Sr. Frontend Engineer →
  Raises PR →
  Notifies human when merged
```

The human never needs to explain HOW. They state WHAT they want, and the addressed agent coordinates with its team to deliver.

### 7.3 Feedback Integration

When the human provides feedback to any agent:
1. The agent acknowledges and interprets the feedback
2. The agent discusses with its direct manager and relevant peers
3. If the feedback implies a systemic issue, it escalates to VP Eng
4. The fix is implemented, reviewed, and deployed through the normal PR cycle
5. The CPO evaluates whether the feedback reveals a gap in requirements understanding and updates acceptance criteria

---

## 8. Technology Stack

### 8.1 Orchestration Layer
- **LangGraph**: DAG construction, state management, conditional routing, human-in-the-loop checkpoints
- **LangGraph Cloud** (optional): For managed deployment and monitoring
- **Redis**: Agent state persistence, task queues, cost tracking
- **PostgreSQL**: Persistent storage for workflow history, cost data, optimization patterns

### 8.2 Agent Communication
- **LangGraph State**: Primary state passing between nodes
- **Structured Message Protocol**: JSON-based inter-agent communication with typed schemas
- **Event Bus**: For async notifications (PR raised, review complete, build status)

### 8.3 Model Providers
- **Anthropic API**: Opus, Sonnet, Haiku (primary)
- **Google AI API**: Gemini (visual/multimodal tasks)
- **OpenAI API**: o3 (systems consulting)

### 8.4 Development Infrastructure
- **Git**: Version control with branch-per-feature workflow
- **GitHub Actions / CI**: Automated build, test, lint on every PR
- **Docker**: Containerized test environments for all supported languages
- **Language-Specific Tooling**: ESLint, Prettier, Black, Rubocop, golangci-lint, etc.

### 8.5 Editor Integration (Neovim)
- Custom Lua plugin for NEXUS communication
- Terminal buffers for agent stream monitoring
- Telescope integration for searching agent logs
- Status line showing active workstreams, cost burn rate, agent activity

---

## 9. Supported Language Matrix

| Language | Implementation Agent | Linter | Test Framework | Notes |
|----------|---------------------|--------|----------------|-------|
| TypeScript | Frontend/Full-Stack | ESLint + Prettier | Jest/Vitest | Primary frontend language |
| JavaScript | Frontend/Full-Stack | ESLint + Prettier | Jest/Vitest | Legacy support |
| Python | Backend (Scripting) | Ruff + Black | pytest | AI/ML, scripting, APIs |
| Java | Backend (JVM) | Checkstyle + SpotBugs | JUnit 5 | Enterprise services |
| Go | Backend (Systems) | golangci-lint | go test | Performance-critical services |
| C# | Backend (JVM) | dotnet format + analyzers | xUnit | .NET services |
| C | Backend (Systems) | clang-tidy | CUnit | Systems programming |
| C++ | Backend (Systems) | clang-tidy + cppcheck | Google Test | Performance-critical code |
| Ruby | Backend (Scripting) | Rubocop | RSpec | Rails applications |
| PHP | Backend (Scripting) | PHP_CodeSniffer + PHPStan | PHPUnit | Web applications |
| HTML/CSS | Frontend | HTMLHint + Stylelint | Playwright | Markup and styling |
| HTMX | Frontend | HTMLHint | Playwright | Hypermedia-driven UI |
| Next.js | Full-Stack | ESLint + Prettier | Jest + Playwright | Full-stack React framework |
| Node.js | Backend (Scripting) | ESLint | Jest/Vitest | Server-side JS |

---

## 10. Auto-Fork Parallel Execution Model

### 10.1 Fork Detection

The orchestrator analyzes the execution DAG and identifies independent workstreams:

```python
# Simplified fork detection logic
def identify_forks(dag: ExecutionDAG) -> list[Workstream]:
    """
    A workstream can be forked if:
    1. It has no data dependency on other pending workstreams
    2. It operates on different files/modules
    3. Its API contracts are already defined (no blocking on interface design)
    """
    independent_nodes = []
    for node in dag.pending_nodes:
        dependencies = dag.get_dependencies(node)
        if all(dep.status == "complete" for dep in dependencies):
            independent_nodes.append(node)
    
    return group_into_workstreams(independent_nodes)
```

### 10.2 Fork Execution

Each fork runs as an independent LangGraph subgraph with:
- Its own agent assignments
- Its own token budget (allocated by CFO)
- Its own review cycle
- Shared access to the codebase (with conflict detection)

### 10.3 Merge Protocol

When parallel forks complete:
1. **Conflict Detection**: Automated check for file-level conflicts
2. **Integration Testing**: Full-Stack Sr. Engineer runs integration tests across fork boundaries
3. **Merge Order**: Determined by dependency graph (independent forks merge in any order)
4. **Conflict Resolution**: If forks modified the same file, Sr. Full-Stack Engineer manually reconciles

---

## 11. Self-Improving Collaboration Model

### 11.1 Working Relationship Registry

Agents build a persistent record of how they work best together:

```json
{
  "pair": ["frontend-dev", "sr-frontend-engineer"],
  "observed_patterns": {
    "first_pass_approval_rate": 0.73,
    "common_revision_reasons": ["missing error states", "inconsistent spacing"],
    "optimal_spec_detail_level": "high — frontend dev performs better with explicit breakpoint specs",
    "communication_style": "frontend dev prefers specific CSS property suggestions over vague 'fix the spacing'"
  },
  "adaptations": [
    "Sr. engineer now includes specific pixel values in review feedback",
    "Frontend dev now includes all breakpoint screenshots in PR"
  ]
}
```

### 11.2 Continuous Improvement Cycle

**Weekly (automated):**
- Cost Optimization Consultant generates efficiency report
- CFO reviews and adjusts budgets
- CRO identifies throughput bottlenecks

**Per-Project (automated):**
- VP Eng conducts retrospective: What worked? What didn't?
- Working relationship registries updated
- Agent prompt/system-message refinements proposed and tested

**Triggered by repeated failures:**
- If an agent type consistently fails at a task type, the system:
  1. Analyzes failure patterns
  2. Tests whether a different model or approach works better
  3. Updates routing rules accordingly
  4. Documents the change and rationale

---

## 12. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-3)
- [ ] LangGraph graph structure with basic routing
- [ ] Executive layer agents (CEO, CFO, CPO, CRO) with system prompts
- [ ] Basic orchestrator with sequential execution
- [ ] Token cost tracking infrastructure
- [ ] Neovim plugin skeleton (Lua)

### Phase 2: Parallel Execution (Weeks 4-6)
- [ ] Auto-fork detection and parallel workstream execution
- [ ] Haiku swarm manager (spawn, monitor, collect results)
- [ ] Merge protocol for parallel forks
- [ ] PR automation (raise, assign reviewers, process feedback)

### Phase 3: Multi-Model Integration (Weeks 7-8)
- [ ] Gemini integration for visual QA
- [ ] OpenAI o3 integration for systems consulting
- [ ] Model routing logic (which model for which task)
- [ ] Cross-provider cost normalization

### Phase 4: Quality & Governance (Weeks 9-10)
- [ ] Full linting pipeline across all 14 languages
- [ ] Test generation and quality validation
- [ ] Documentation generation and auto-update pipeline
- [ ] Governance gates and PR review workflow

### Phase 5: Self-Optimization (Weeks 11-12)
- [ ] Working relationship registry
- [ ] Cost optimization analysis pipeline
- [ ] Agent workflow self-adjustment
- [ ] Efficiency dashboards and reporting

### Phase 6: Neovim Integration (Weeks 13-14)
- [ ] Full Lua plugin with agent communication
- [ ] Terminal buffer monitoring for active workstreams
- [ ] Direct agent addressing from editor
- [ ] Status line with cost burn rate and agent activity

---

## Appendix A: Agent Communication Schema

```typescript
interface AgentMessage {
  from: AgentId;
  to: AgentId | "broadcast";
  type: "task" | "review" | "feedback" | "escalation" | "status" | "cost_alert";
  priority: "critical" | "high" | "normal" | "low";
  payload: {
    context: string;          // What the agent needs to know
    instruction: string;      // What the agent should do
    constraints: string[];    // Budget, time, quality constraints
    artifacts?: string[];     // File paths, PR links, test results
  };
  metadata: {
    timestamp: string;
    token_cost: number;
    workstream_id: string;
    parent_message_id?: string;
  };
}
```

## Appendix B: Token Cost Reference (Approximate)

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Best For |
|-------|----------------------|------------------------|----------|
| Opus | $15.00 | $75.00 | Strategic decisions, debugging approach, complex reasoning |
| Sonnet | $3.00 | $15.00 | Implementation, review, documentation |
| Haiku | $0.25 | $1.25 | Swarm tasks, linting, doc updates, formatting |
| Gemini | ~$1.25 | ~$5.00 | Visual validation, multimodal analysis |
| o3 | ~$10.00 | ~$40.00 | Systems architecture consulting |

*CFO uses these rates to calculate per-task budgets and track actual vs. projected spend.*

# NEXUS: Architecture Specification v1.1 — Addendum

## Changes from v1.0

This addendum covers: Type Safety Enforcement, Escalation Protocol, Budget & Cost Model, KPI/OKR System, Security Hardening, Environment Management, Cross-Platform Support, and Bootstrapping.

---

## 13. Type Safety Enforcement & Anti-Pattern Governance

### 13.1 The `any` Ban

`type: any` is treated as a **build-breaking violation**. It is never acceptable, under any circumstances, for any reason. The system enforces this at multiple layers:

**Layer 1 — Linting (Pre-Commit)**
```json
// tsconfig.json — enforced on every project
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "strictFunctionTypes": true,
    "strictBindCallApply": true,
    "strictPropertyInitialization": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true
  }
}

// ESLint rules — zero tolerance
{
  "@typescript-eslint/no-explicit-any": "error",
  "@typescript-eslint/no-unsafe-assignment": "error",
  "@typescript-eslint/no-unsafe-call": "error",
  "@typescript-eslint/no-unsafe-member-access": "error",
  "@typescript-eslint/no-unsafe-return": "error",
  "@typescript-eslint/no-unsafe-argument": "error"
}
```

**Layer 2 — PR Review Gate**
The Sr. Engineers and Linting Agent run a specific scan for `any` usage. If found, the PR is auto-rejected with no further review. The implementing agent must fix it before resubmission.

**Layer 3 — Root Cause Analysis**
If an agent attempts to use `any`, the system logs WHY. Common causes and required responses:

| Root Cause | Required Response |
|-----------|-------------------|
| Third-party library has no types | Write a `.d.ts` declaration file or use `@types/` package |
| Complex generic inference | Use explicit generic parameters, not `any` |
| Union type too complex | Break into discriminated union or branded types |
| API response shape unknown | Define a Zod/io-ts schema and validate at runtime |
| "I don't know the type" | This is never acceptable. Research the type. Ask a peer. |

### 13.2 Comprehensive Anti-Pattern Registry

The system maintains a living anti-pattern registry. Agents are trained to recognize AND avoid these. This isn't just TypeScript — it covers all supported languages.

**TypeScript/JavaScript Anti-Patterns:**
- `any` / `as any` / `@ts-ignore` / `@ts-expect-error` (without documented justification)
- `!` non-null assertions (use proper null checks)
- `== null` instead of `=== null || === undefined` (or better: optional chaining)
- Mutable global state
- `console.log` in production code (use structured logging)
- Barrel imports that break tree-shaking
- `eval()` or `new Function()` — always forbidden
- Inline styles in React (use CSS modules, Tailwind, or styled-components)
- `dangerouslySetInnerHTML` without sanitization
- Unhandled promise rejections
- Missing error boundaries in React

**Python Anti-Patterns:**
- Bare `except:` (must specify exception type)
- Mutable default arguments
- `import *`
- SQL string concatenation (use parameterized queries)
- `pickle` for untrusted data
- `os.system()` (use `subprocess.run()`)

**Cross-Language Anti-Patterns:**
- Hardcoded secrets, API keys, connection strings
- SQL injection vectors
- Unvalidated user input reaching DB/filesystem/shell
- Missing rate limiting on API endpoints
- Missing input length limits
- Logging PII or secrets
- Trusting client-side validation alone

**Enforcement**: The Linting & Standards Agent (Haiku) runs anti-pattern scans on every file change. Violations are blocking — the PR cannot proceed.

### 13.3 Collaborative Escalation Protocol for Type Challenges

When an agent encounters a type that it cannot resolve:

```
Agent encounters type challenge
       │
       ▼
┌─────────────────────┐
│  SELF-ATTEMPT        │  Agent tries 3 approaches:
│  (Sonnet)            │  1. Explicit generics
│  Max: 3 attempts     │  2. Type narrowing / guards
│  Budget: 500 tokens  │  3. Discriminated unions
└──────┬──────────────┘
       │ Still unresolved?
       ▼
┌─────────────────────┐
│  PEER ASSIST         │  Loop in a Sonnet peer:
│  (Sonnet + Sonnet)   │  - Sr. Frontend or Sr. Backend engineer
│  Max: 3 attempts     │  - They pair-debug the type
│  Budget: 1000 tokens │  - Try conditional types, mapped types, infer
└──────┬──────────────┘
       │ Still unresolved?
       ▼
┌─────────────────────┐
│  OPUS ESCALATION     │  Loop in the Tech Lead (Opus):
│  (Opus + Sonnets)    │  - Deep type-level reasoning
│  Max: 2 attempts     │  - May redesign the interface
│  Budget: 2000 tokens │  - May determine the API design is wrong
└──────┬──────────────┘
       │ Still unresolved?
       ▼
┌─────────────────────┐
│  ARCHITECTURE        │  VP Eng + Tech Lead:
│  REVIEW              │  - The type might be unsolvable because
│                      │    the architecture is wrong
│                      │  - Redesign the interface/contract
│                      │  - This is a FEATURE, not a bug —
│                      │    impossible types reveal design problems
└─────────────────────┘
```

**Critical Rule**: At NO point in this escalation chain is `any` an acceptable resolution. The type challenge must be solved with a proper type, or the architecture must change. The system treats "I can't type this" as "this design needs to change."

---

## 14. Budget & Cost Model

### 14.1 Garrett's Actual Budget

| Resource | Monthly Cost | Access Method |
|----------|-------------|---------------|
| Claude Max | $200/month | Subscription — includes Opus, Sonnet, Haiku via claude.ai / API |
| ChatGPT Plus | $20/month | Subscription — access to o3 and GPT-4o |
| Gemini | Free tier / API | Use free tier where possible, API for visual QA |
| **Total** | **$220/month** | |

### 14.2 Per-Project Cost Target

**Target: ~$1/hour aggregate API cost per active project**

This means if a project runs 8 hours of agent activity, it should cost roughly $8 in API tokens (above the subscription).

To achieve this, the system uses aggressive cost metering:

**Token Budget Strategy:**
```
Hourly Budget: ~$1.00

Allocation per hour:
├── Opus:   ~$0.30  →  ~4K input + ~2K output tokens/hr
├── Sonnet: ~$0.40  →  ~90K input + ~15K output tokens/hr  
├── Haiku:  ~$0.20  →  ~500K input + ~100K output tokens/hr
└── Gemini/o3: ~$0.10 → Used sparingly for consulting tasks

Monthly project cap at 40hr/week: ~$160 in API costs
Total with subscriptions: ~$380/month
```

### 14.3 Cost-Saving Strategies

**Maximize Subscription Value:**
- Route as much work as possible through Claude Max subscription (Opus/Sonnet/Haiku included in $200/month)
- Use ChatGPT subscription for o3 consulting where possible before hitting API
- Gemini free tier for most visual QA tasks

**Intelligent Model Routing:**
- Default to Haiku for all well-specified tasks
- Only escalate to Sonnet when Haiku fails or task requires reasoning
- Only use Opus for strategic decisions, debugging approach, and type escalation
- Cache common patterns and reuse (don't re-reason solved problems)

**Metering & Throttling:**
- CFO agent tracks cumulative hourly cost
- If approaching $1/hr threshold, CFO switches to "efficiency mode":
  - Pause non-critical workstreams
  - Batch Haiku tasks to reduce API call overhead
  - Defer documentation updates to next idle period
  - Skip optional quality passes (keep mandatory ones)
- If a task is projected to exceed budget, CFO flags it and the system meters execution speed to stay within bounds

**Context Window Optimization:**
- Haiku agents receive minimal, focused context (not the full codebase)
- Use file path references instead of full file contents where possible
- Summarize long conversation histories before passing to next agent
- Prune irrelevant context aggressively

### 14.4 Subscription vs. API Decision Logic

```
Task arrives
     │
     ▼
Can this be done through Claude Max subscription?
     ├── YES → Route through subscription (no marginal cost)
     │
     └── NO (need parallel execution / programmatic access)
          │
          ▼
     Is this a Haiku-eligible task?
          ├── YES → API Haiku ($0.25/$1.25 per 1M tokens — very cheap)
          │
          └── NO → Use cheapest capable model via API
```

---

## 15. KPI/OKR System & `/KPI` Command

### 15.1 System-Set KPIs

The system establishes and tracks these KPIs automatically:

**Productivity KPIs:**
| KPI | Target | Measurement |
|-----|--------|-------------|
| First-Pass PR Approval Rate | >75% | PRs approved without revision / total PRs |
| Mean Time to Feature Completion | Tracked per complexity tier | Clock time from objective to merged code |
| Parallel Workstream Utilization | >60% | Time spent in parallel execution / total execution time |
| Agent Idle Rate | <15% | Time agents wait for dependencies / total time |
| Lines of Meaningful Code per Dollar | Tracked (trending up) | LOC excluding boilerplate / API cost |

**Quality KPIs:**
| KPI | Target | Measurement |
|-----|--------|-------------|
| Anti-Pattern Violations per 1K LOC | <0.5 | Violations caught in review / total KLOC |
| `any` Usage Count | **0** (absolute) | Instances found in codebase scans |
| CVE Count in Dependencies | 0 critical, 0 high | Automated dependency scanning |
| Test Coverage (meaningful) | >80% | Meaningful tests / testable code paths |
| Visual QA Pass Rate | >90% | UI implementations passing Gemini visual check on first attempt |
| Linting Pass Rate on First Commit | >85% | Clean lint results on first attempt |

**Cost KPIs:**
| KPI | Target | Measurement |
|-----|--------|-------------|
| Hourly API Cost (aggregate) | ≤$1.00 | Rolling average API spend per active hour |
| Cost per Feature (by complexity) | Tracked (trending down) | Total tokens for a feature / feature complexity score |
| Haiku Task Success Rate | >85% | Haiku-completed tasks not requiring Sonnet escalation |
| Wasted Token Rate | <10% | Tokens spent on failed approaches / total tokens |
| Escalation Rate | <15% | Tasks requiring model upgrade / total tasks |

**Security KPIs:**
| KPI | Target | Measurement |
|-----|--------|-------------|
| Dependency Vulnerabilities | 0 critical/high | `npm audit`, `pip audit`, `cargo audit`, etc. |
| Secrets in Codebase | **0** (absolute) | Automated secret scanning |
| SOC 2 Control Coverage | Tracked (approaching 100%) | Controls implemented / controls required |

### 15.2 OKRs (Quarterly, Self-Set)

The CEO agent sets quarterly OKRs for the organization. Example:

```
Q1 OKR: Establish Reliable Autonomous Delivery

Objective 1: Achieve consistent first-pass quality
  KR1: First-pass PR approval rate >75%
  KR2: Zero `any` usage across all TypeScript codebases
  KR3: Meaningful test coverage >80%

Objective 2: Optimize cost efficiency
  KR1: Reduce average hourly API cost to <$0.80
  KR2: Increase Haiku task success rate to >90%
  KR3: Reduce wasted token rate to <8%

Objective 3: Harden security posture
  KR1: Zero critical/high CVEs in any project
  KR2: Implement 100% of SOC 2 Type II technical controls
  KR3: Pass automated penetration test suite
```

### 15.3 `/KPI` Command

When Garrett types `/KPI`, the system generates:

```
═══════════════════════════════════════════════
  NEXUS Performance Dashboard — 2026-02-10
═══════════════════════════════════════════════

📊 PRODUCTIVITY
  First-Pass PR Approval:    78% ✅ (target: >75%)
  Mean Feature Completion:   2.3hrs (small) / 8.1hrs (medium)
  Parallel Utilization:      64% ✅ (target: >60%)
  Agent Idle Rate:           12% ✅ (target: <15%)

🛡️ QUALITY  
  Anti-Pattern Violations:   0.3/KLOC ✅ (target: <0.5)
  `any` Count:               0 ✅ (ZERO TOLERANCE)
  CVEs (critical/high):      0/0 ✅
  Meaningful Test Coverage:  83% ✅ (target: >80%)
  Visual QA First-Pass:      88% ⚠️ (target: >90%)

💰 COST
  Hourly API Cost (avg):     $0.87 ✅ (target: ≤$1.00)
  This Session Cost:         $3.41 (3.9 hrs active)
  Month-to-Date API Cost:    $47.20
  Projected Monthly Total:   $168 (within budget ✅)
  Haiku Success Rate:        87% ✅ (target: >85%)
  Wasted Token Rate:         9% ✅ (target: <10%)

🔒 SECURITY
  Dependency Vulns:          0 ✅
  Secrets Detected:          0 ✅
  SOC 2 Control Coverage:    72% 🔄 (tracking toward 100%)

📈 OKR PROGRESS (Q1 2026)
  Obj 1 — First-Pass Quality:     82% complete
  Obj 2 — Cost Efficiency:        67% complete
  Obj 3 — Security Hardening:     72% complete

⚠️ ATTENTION ITEMS:
  • Visual QA first-pass rate trending below target — 
    Eng Manager Frontend investigating CSS variable inheritance 
    issues as root cause
  • SOC 2 control coverage on track but needs encryption-at-rest 
    implementation for data stores
═══════════════════════════════════════════════
```

Additional commands:
- `/KPI detail` — Full breakdown with per-agent performance
- `/KPI cost` — Detailed cost report with per-model breakdown
- `/KPI security` — Full security posture report
- `/KPI trends` — Week-over-week trend graphs

---

## 16. Security Hardening — SOC 2 Type II Ready

### 16.1 Security Philosophy

Every project NEXUS builds is designed as if it will undergo a SOC 2 Type II audit. This isn't optional — it's the default baseline.

### 16.2 Security Controls (Mapped to SOC 2 Trust Service Criteria)

**CC6.1 — Logical & Physical Access Controls:**
- All API endpoints require authentication (no anonymous access by default)
- Role-based access control (RBAC) implemented from day one
- JWT tokens with short expiry + refresh token rotation
- Session management with server-side validation
- Rate limiting on all endpoints (configurable per-route)
- Account lockout after failed attempts
- CORS configured to explicit allowed origins only (never `*` in production)

**CC6.6 — Encryption:**
- TLS 1.3 enforced for all data in transit (no fallback to TLS 1.2)
- AES-256-GCM for all data at rest
- Database encryption enabled by default
- Secrets encrypted in environment (never plaintext in config files)
- End-to-end encryption for sensitive data flows
- Certificate pinning for critical API connections
- Signed data payloads where integrity is critical (HMAC-SHA256)

**CC6.7 — Data Integrity:**
- Input validation at every boundary (API, form, file upload, webhook)
- Parameterized queries only (no string concatenation in SQL, ever)
- Content Security Policy (CSP) headers
- X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security headers
- Subresource Integrity (SRI) for all external scripts
- Output encoding for all user-generated content

**CC6.8 — Vulnerability Management:**
- Automated dependency scanning on every build (`npm audit`, `pip audit`, `cargo audit`, `snyk`)
- SAST (Static Application Security Testing) integrated into CI
- Secret scanning in every commit (detect-secrets, trufflehog)
- Container image scanning if Docker is used
- Known CVE database checked daily
- Zero tolerance for critical/high vulnerabilities — build fails

**CC7.2 — Monitoring & Detection:**
- Structured logging with correlation IDs
- Security event logging (auth failures, permission denials, unusual patterns)
- Log integrity (append-only, tamper-evident)
- Alerting on anomalous patterns

**CC8.1 — Change Management:**
- All changes through PR process (no direct commits to main)
- Required reviews from Sr. Engineers
- Automated test suite must pass before merge
- Deployment through CI/CD only (no manual deploys)
- Rollback capability for every deployment

### 16.3 Security Scanning Pipeline

```
Code Change
     │
     ▼
┌─────────────────┐
│  SECRET SCAN    │  trufflehog + detect-secrets
│                 │  Checks for API keys, passwords, tokens
│                 │  in code, configs, comments, .env files
└──────┬──────────┘
       │ Pass?
       ▼
┌─────────────────┐
│  SAST SCAN      │  semgrep + language-specific analyzers
│                 │  SQL injection, XSS, path traversal,
│                 │  command injection, insecure deserialization
└──────┬──────────┘
       │ Pass?
       ▼
┌─────────────────┐
│  DEPENDENCY     │  npm audit + pip audit + snyk
│  SCAN           │  Known CVEs in all dependencies
│                 │  License compliance check
└──────┬──────────┘
       │ Pass?
       ▼
┌─────────────────┐
│  SECURITY       │  Opus Security Consultant reviews:
│  CONSULTANT     │  - Auth flow correctness
│  REVIEW         │  - Data exposure risks
│  (for PRs with  │  - Encryption implementation
│  auth/data/API  │  - OWASP Top 10 checklist
│  changes)       │
└──────┬──────────┘
       │ All pass?
       ▼
  PR continues to normal review
```

### 16.4 Dependency Management

- Lock files committed for all package managers (`package-lock.json`, `poetry.lock`, `go.sum`, etc.)
- Automated dependency updates (Dependabot/Renovate) with test verification
- No `*` version ranges — all dependencies pinned to exact versions
- New dependency additions require Security Consultant review
- Preference for well-maintained, widely-used packages over obscure ones
- Minimize dependency count — if something can be written in <50 lines, don't import a package

---

## 17. Environment & CLI Management

### 17.1 Philosophy

Garrett should never need to manually configure CLI tools, PATH variables, or environment files. NEXUS handles all of this automatically during project bootstrapping.

### 17.2 Automatic Environment Setup

When NEXUS bootstraps a project, it:

1. **Detects the OS** (macOS / Windows) and adapts all commands accordingly
2. **Checks for required tools** and installs missing ones:
   ```
   macOS: Uses Homebrew (installs if missing)
   Windows: Uses winget, chocolatey, or scoop
   ```
3. **Sets up the project environment:**
   - Creates `.env`, `.env.local`, `.env.development`, `.env.production` files
   - Populates with safe defaults and placeholder values
   - Sets correct PATH entries for project-specific tools
   - Configures shell profiles (`~/.zshrc` on Mac, PowerShell profile on Windows)

4. **API Key Collection** — when NEXUS needs API keys:
   ```
   ╔══════════════════════════════════════════════╗
   ║  NEXUS needs the following API keys.         ║
   ║  Please paste each one when prompted:        ║
   ║                                              ║
   ║  1. Anthropic API Key (for agent execution)  ║
   ║     → Get from: console.anthropic.com        ║
   ║                                              ║
   ║  2. Google AI API Key (for Gemini)           ║
   ║     → Get from: aistudio.google.com          ║
   ║                                              ║
   ║  3. OpenAI API Key (for o3)                  ║
   ║     → Get from: platform.openai.com          ║
   ║                                              ║
   ║  NEXUS will store these in:                  ║
   ║    ~/.nexus/.env.keys (encrypted, 600 perms) ║
   ╚══════════════════════════════════════════════╝
   ```
   - Keys are stored encrypted, never in plaintext
   - Keys are referenced via environment variables, never hardcoded
   - Keys are automatically injected into project `.env` files via symlinks/references
   - Garrett pastes keys ONCE; NEXUS handles the rest forever

### 17.3 CLI Abstraction

NEXUS provides a single CLI entry point:

```bash
# Install NEXUS
curl -fsSL https://nexus.dev/install.sh | sh   # macOS/Linux
irm https://nexus.dev/install.ps1 | iex         # Windows PowerShell

# Usage
nexus init <project-name>          # Bootstrap new project
nexus start                        # Start agent orchestration
nexus status                       # Show active workstreams
nexus kpi                          # Show KPI dashboard
nexus cost                         # Show cost report
nexus talk @<agent-name>           # Direct message an agent
nexus logs                         # Stream agent activity logs
nexus stop                         # Pause all workstreams
nexus resume                       # Resume paused workstreams
```

### 17.4 Project Bootstrapping

`nexus init` handles EVERYTHING:

```
nexus init my-saas-app
     │
     ▼
┌──────────────────────────────────┐
│  1. DETECT ENVIRONMENT           │
│     - OS: macOS 14.2 / Win 11   │
│     - Shell: zsh / PowerShell    │
│     - Node: v20.11 (or install)  │
│     - Python: 3.12 (or install)  │
│     - Git: 2.43 (or install)     │
│     - Docker: (or install)       │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│  2. SCAFFOLD PROJECT             │
│     - Git repo initialized       │
│     - .gitignore (comprehensive) │
│     - Package manager setup      │
│     - TypeScript config (strict) │
│     - Linting config             │
│     - Test framework setup       │
│     - CI/CD pipeline             │
│     - Docker setup               │
│     - Security scanning config   │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│  3. ENVIRONMENT CONFIGURATION    │
│     - .env files created         │
│     - API keys injected from     │
│       encrypted store            │
│     - PATH configured            │
│     - Shell aliases added        │
│     - Editor config (.editorconf)│
│     - Git hooks (pre-commit)     │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│  4. SECURITY BASELINE            │
│     - Pre-commit hooks:          │
│       secret scan, lint, format  │
│     - CSP headers template       │
│     - Auth scaffold              │
│     - HTTPS enforcement          │
│     - Security headers           │
│     - Dependency audit baseline   │
└──────────────────────────────────┘
```

---

## 18. Cross-Platform Support

### 18.1 Supported Platforms

| Platform | Support Level | Notes |
|----------|--------------|-------|
| macOS (Apple Silicon + Intel) | Full | Primary development |
| Windows 10/11 | Full | WSL2 recommended for some tools |
| Linux (Ubuntu/Debian) | Full | Server/CI environments |
| Mobile (Happy Coder) | Remote execution | Connects to running NEXUS instance on home machine |

### 18.2 Remote Execution (Happy Coder / Mobile)

When Garrett is away but his machine is online:

```
┌─────────────┐          ┌──────────────────┐
│  Mobile     │  ──────► │  Home Machine    │
│  (Happy     │  HTTPS   │  (macOS/Windows) │
│   Coder)    │  WSS     │                  │
│             │  ◄────── │  NEXUS running   │
│  Send       │          │  as background   │
│  objectives │          │  service/daemon  │
│  View KPIs  │          │                  │
│  Talk to    │          │  Full agent      │
│  agents     │          │  orchestration   │
└─────────────┘          └──────────────────┘
```

**Setup:**
- NEXUS runs as a daemon/service on the home machine
- Exposes a secure API (mTLS) for remote control
- Happy Coder connects via this API
- All computation happens on the home machine
- Mobile only sends commands and receives status/results

### 18.3 Platform-Specific Adaptations

The DevOps agent automatically adapts commands and tooling per platform:

| Concern | macOS | Windows |
|---------|-------|---------|
| Package manager | Homebrew | winget/chocolatey |
| Shell | zsh | PowerShell 7 |
| Path separator | `/` | `\` (but agents use path.join()) |
| Docker | Docker Desktop | Docker Desktop / WSL2 |
| Node.js | via nvm | via nvm-windows |
| Python | via pyenv | via pyenv-win |
| Git | Xcode CLT | Git for Windows |
| Terminal | iTerm2 / built-in | Windows Terminal |
| Neovim config | `~/.config/nvim/` | `~/AppData/Local/nvim/` |

---

## 19. Pattern Adherence System

### 19.1 How the System Learns from AI's Statistical Biases

AI models reproduce common human patterns — including bad ones. The system explicitly counteracts this:

| AI Statistical Bias | Human Origin | NEXUS Countermeasure |
|--------------------|--------------|----------------------|
| `type: any` when types get hard | Developers take shortcuts under pressure | Absolute ban. Escalation protocol instead. |
| Overly complex abstractions | "Architecture astronaut" patterns in training data | CPO validates: "Does this complexity serve the user?" |
| Missing error handling | Happy-path focus in tutorials/examples | QA Lead requires error path tests for every feature |
| Generic CSS that breaks in edge cases | Copy-paste from Stack Overflow | Gemini visual QA across all states and breakpoints |
| Excessive npm dependencies | npm install culture | Security Consultant reviews all new deps; <50 LOC = write it yourself |
| `console.log` debugging | Ubiquitous in JS training data | Structured logging enforced; console.log fails lint |
| Catch-all error handlers | `catch(e) {}` everywhere in OSS | Must handle specific error types with appropriate responses |
| Missing accessibility | Most training data ignores a11y | WCAG AA minimum enforced by Gemini visual QA |
| Insecure defaults | Training data full of tutorials without security | SOC 2 controls applied from project init |

### 19.2 Continuous Anti-Pattern Learning

When a new anti-pattern is discovered (either by the system or by Garrett's feedback), it is:

1. Documented with: pattern description, why it's bad, what to do instead
2. Added to the anti-pattern registry
3. A lint rule is created if possible
4. All agents are updated via their system prompts
5. Existing codebases are scanned and remediated
6. The discovery is tracked as a KPI improvement

---

## 20. Updated Implementation Roadmap

### Phase 0: CLI & Environment (Week 1)
- [ ] NEXUS CLI tool (`nexus` command)
- [ ] Cross-platform installer (macOS + Windows)
- [ ] API key collection and encrypted storage
- [ ] Environment detection and tool installation
- [ ] Project bootstrapping (`nexus init`)

### Phase 1: Foundation (Weeks 2-4)
- [ ] LangGraph graph structure with basic routing
- [ ] Executive layer agents with system prompts
- [ ] Basic orchestrator with sequential execution
- [ ] Token cost tracking with $1/hr metering
- [ ] KPI tracking infrastructure
- [ ] `/KPI` command implementation

### Phase 2: Type Safety & Quality (Weeks 5-6)
- [ ] Anti-pattern registry and scanning
- [ ] TypeScript strict mode enforcement
- [ ] Escalation protocol (Sonnet → Sonnet peer → Opus)
- [ ] Security scanning pipeline
- [ ] SOC 2 control implementation (phase 1)

### Phase 3: Parallel Execution (Weeks 7-9)
- [ ] Auto-fork detection and parallel workstreams
- [ ] Haiku swarm manager
- [ ] PR automation and governance gates
- [ ] Merge protocol for parallel forks

### Phase 4: Multi-Model & Visual QA (Weeks 10-11)
- [ ] Gemini integration for visual validation
- [ ] OpenAI o3 integration for systems consulting
- [ ] Cross-provider cost normalization
- [ ] Frontend visual QA pipeline

### Phase 5: Self-Optimization (Weeks 12-13)
- [ ] Working relationship registry
- [ ] Cost optimization loop
- [ ] OKR system (CEO sets quarterly)
- [ ] Agent workflow self-adjustment

### Phase 6: Remote & Neovim (Weeks 14-16)
- [ ] NEXUS daemon for background execution
- [ ] Remote API for Happy Coder / mobile access
- [ ] Neovim Lua plugin
- [ ] Agent monitoring and direct addressing from editor

---

## Appendix C: `/commands` Reference

| Command | Description |
|---------|-------------|
| `/KPI` | Current KPI dashboard |
| `/KPI detail` | Per-agent performance breakdown |
| `/KPI cost` | Detailed cost report |
| `/KPI security` | Security posture report |
| `/KPI trends` | Week-over-week trends |
| `/status` | Active workstreams and agent activity |
| `/cost` | Current session and projected costs |
| `/talk @agent` | Direct message a specific agent |
| `/pause` | Pause all workstreams |
| `/resume` | Resume paused workstreams |
| `/budget set <amount>` | Override hourly budget |
| `/security audit` | Run full security scan |
| `/antipattern add <desc>` | Add new anti-pattern to registry |
| `/bootstrap` | Re-run environment setup |

# NEXUS: Architecture Specification v1.2 — Addendum

## Changes from v1.1

This addendum covers: GitHub Repository & Self-Committing, Resource & Capacity Tracking, CEO Interaction Model, Slash Command System (Claude Code Plugin Architecture), and Claude Code Plugin Discovery.

---

## 21. GitHub Repository & Self-Committing Behavior

### 21.1 Repository Structure

NEXUS lives as its own repo under Garrett's GitHub organization:

```
github.com/Garrett-s-Apps/nexus
├── .claude-plugin/
│   └── plugin.json                # Claude Code plugin manifest
├── .claude/
│   └── settings.json              # Claude Code project settings
├── agents/
│   ├── executive/
│   │   ├── ceo.md
│   │   ├── cfo.md
│   │   ├── cpo.md
│   │   └── cro.md
│   ├── management/
│   │   ├── vp-engineering.md
│   │   ├── tech-lead.md
│   │   ├── em-frontend.md
│   │   ├── em-backend.md
│   │   └── em-platform.md
│   ├── senior/
│   │   ├── sr-frontend.md
│   │   ├── sr-backend.md
│   │   ├── sr-fullstack.md
│   │   └── sr-devops.md
│   ├── implementation/
│   │   ├── frontend-dev.md
│   │   ├── backend-jvm.md
│   │   ├── backend-scripting.md
│   │   ├── fullstack-dev.md
│   │   └── devops-engineer.md
│   ├── quality/
│   │   ├── qa-lead.md
│   │   ├── test-frontend.md
│   │   ├── test-backend.md
│   │   └── linting-standards.md
│   └── consultants/
│       ├── ux-consultant.md        # Gemini
│       ├── systems-consultant.md   # OpenAI o3
│       ├── security-consultant.md
│       ├── devops-consultant.md
│       └── cost-consultant.md
├── commands/
│   ├── kpi.md
│   ├── status.md
│   ├── cost.md
│   ├── talk.md
│   ├── security-audit.md
│   ├── bootstrap.md
│   ├── demo.md
│   └── deploy.md
├── skills/
│   ├── type-safety/
│   │   └── SKILL.md
│   ├── anti-pattern-detection/
│   │   └── SKILL.md
│   ├── security-hardening/
│   │   └── SKILL.md
│   ├── cost-optimization/
│   │   └── SKILL.md
│   ├── visual-qa/
│   │   └── SKILL.md
│   └── documentation/
│       └── SKILL.md
├── hooks/
│   ├── hooks.json
│   └── scripts/
│       ├── pre-commit-scan.sh
│       ├── post-commit-doc-update.sh
│       ├── cost-tracker.py
│       └── anti-pattern-check.py
├── src/
│   ├── orchestrator/
│   │   ├── graph.py                # LangGraph DAG definition
│   │   ├── state.py                # Shared state schema
│   │   ├── nodes.py                # Agent node definitions
│   │   ├── router.py               # Conditional routing logic
│   │   └── fork_manager.py         # Parallel execution manager
│   ├── cost/
│   │   ├── tracker.py              # Token cost tracking
│   │   ├── budget.py               # Budget enforcement
│   │   └── optimizer.py            # Self-optimization logic
│   ├── security/
│   │   ├── scanner.py              # CVE/secret/SAST scanning
│   │   ├── dependency_audit.py     # Dependency vulnerability checks
│   │   └── soc2_controls.py        # SOC 2 control enforcement
│   ├── kpi/
│   │   ├── tracker.py              # KPI data collection
│   │   ├── reporter.py             # Dashboard generation
│   │   └── okr_manager.py          # OKR lifecycle
│   ├── git/
│   │   ├── auto_commit.py          # Self-committing logic
│   │   ├── pr_manager.py           # PR creation and management
│   │   └── branch_strategy.py      # Branch naming and management
│   └── resource/
│       ├── capacity_tracker.py     # Track tool/service capacity
│       ├── project_registry.py     # Track all managed projects
│       └── service_limits.py       # Monitor free/paid tier limits
├── config/
│   ├── anti-patterns.yaml          # Anti-pattern registry
│   ├── model-routing.yaml          # Model assignment rules
│   ├── budget-defaults.yaml        # Default budget allocations
│   └── security-controls.yaml      # SOC 2 control definitions
├── docs/
│   ├── ARCHITECTURE.md             # This document (combined v1.0-1.2)
│   ├── AGENT_CATALOG.md            # All agents with capabilities
│   ├── COMMANDS.md                 # All slash commands
│   ├── COST_MODEL.md               # Detailed cost/budget docs
│   └── CHANGELOG.md                # Auto-maintained by system
├── .mcp.json                       # MCP server integrations
├── CLAUDE.md                       # Claude Code project instructions
├── pyproject.toml                  # Python project config
├── package.json                    # Node.js config (for tooling)
└── README.md                       # Public-facing documentation
```

### 21.2 Self-Committing Protocol

NEXUS commits its own changes to itself. Every modification to agent definitions, skills, configs, cost optimization rules, or working relationship data is versioned.

**Commit Rules:**
- NEXUS commits to a `nexus/self-update` branch, never directly to `main`
- Self-updates go through an abbreviated review (Tech Lead auto-reviews)
- Commit messages follow conventional commits: `chore(agents): update sr-frontend prompt based on CSS review patterns`
- Each commit includes a cost tag: `[cost: $0.03]`
- The CHANGELOG.md is auto-updated by Haiku after each merge

**What Gets Committed:**
- Agent prompt refinements (learned from working relationship feedback)
- Anti-pattern registry additions
- Cost optimization rule updates
- KPI/OKR data snapshots (weekly)
- Security control updates
- New skills or skill improvements
- Config changes

**What Does NOT Get Committed to the NEXUS repo:**
- Project-specific code (that goes to the project's repo)
- API keys or secrets (encrypted in `~/.nexus/`)
- Temporary working files

### 21.3 Cross-Project Commit Behavior

When NEXUS works on a project (e.g., RezFix, The Prompt Fixer, Hub 2.0), it commits to THAT project's repo under `Garrett-s-Apps`:

```
Work on RezFix feature
     │
     ▼
Create branch: feature/nexus-<feature-name>
     │
     ▼
Implement → Test → Review (internal)
     │
     ▼
Raise PR on github.com/Garrett-s-Apps/rezfix
     │
     ▼
PR includes:
  - Change summary
  - Test results
  - Cost report
  - Screenshots (if UI)
  - Security scan results
```

---

## 22. Resource & Capacity Tracking

### 22.1 Philosophy

NEXUS's first instinct is always to LOOK, not ask. Before recommending any tool, service, or action, it checks what Garrett currently has, what tier he's on, and what capacity remains.

### 22.2 Known Project Registry

NEXUS maintains awareness of all projects under `Garrett-s-Apps`:

| Repository | Description | Primary Language | Status |
|-----------|-------------|-----------------|--------|
| `claude-multiagent` | Current multi-agent orchestration (predecessor to NEXUS) | JavaScript | Active — to be superseded |
| `sf-story-factory` | Salesforce story generation from unstructured input | JavaScript | Active |
| `nabps-website` | NABPS website | HTML | Active |
| `Hub-2.0-CS` | Blazor Server + C# migration from React | C# / CSS | Active (updated Feb 9) |

NEXUS automatically discovers new repos by checking the GitHub org periodically.

### 22.3 Service Capacity Tracking

NEXUS tracks usage and limits across all services:

```yaml
# config/service-limits.yaml — auto-updated by NEXUS

github:
  plan: "Free (Organization)"
  repos: 4 / unlimited (public)
  actions_minutes:
    included: 2000/month (private repos)
    used_this_month: TBD  # NEXUS checks via API
    strategy: "Use public repos for CI (unlimited free minutes)"
  packages_storage: 500MB included
  pages: available (public repos)
  
github_actions_notes: |
  - Public repos: unlimited free standard runner minutes
  - Private repos: 2000 min/month on Free plan
  - NEXUS strategy: keep repos public, run CI on public repos
  - Self-hosted runners: free (no platform fee on public repos)
  - March 2026 pricing changes may affect private repos

claude:
  plan: "Claude Max"
  monthly_cost: $200
  includes: "Opus, Sonnet, Haiku via claude.ai and Claude Code"
  api_access: "Included with Max plan"
  rate_limits: TBD  # NEXUS checks actual limits

openai:
  plan: "ChatGPT Plus"
  monthly_cost: $20
  includes: "GPT-4o, o3 via chat interface"
  api_access: "Free tier API ($5 credit for new accounts, then pay-as-you-go)"
  strategy: "Use chat subscription for o3 consulting where possible"

gemini:
  plan: "Free tier"
  monthly_cost: $0
  api_limits: "15 RPM, 1500 requests/day, 1M tokens/day"
  strategy: "Sufficient for visual QA tasks"

vercel:
  plan: TBD  # NEXUS checks
  
netlify:
  plan: TBD  # NEXUS checks

docker_hub:
  plan: TBD  # NEXUS checks
```

### 22.4 Capacity Check Protocol

Before recommending ANY external service or tool:

```
NEXUS wants to recommend a tool/service
     │
     ▼
┌──────────────────────────┐
│  1. CHECK: Does Garrett   │
│     already have this?    │
│     (Check GitHub, local  │
│      configs, env vars)   │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  2. CHECK: What tier/plan │
│     is he on?             │
│     (Check via API or     │
│      account pages)       │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  3. CHECK: What capacity  │
│     remains?              │
│     (Check usage vs.      │
│      limits)              │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  4. DECIDE: Can we use    │
│     the free tier?        │
│     Or do we need to      │
│     find an alternative?  │
└──────────────────────────┘
```

**Rule**: NEXUS never recommends a paid upgrade without first exhausting free alternatives and presenting a cost-benefit analysis to the CFO agent.

---

## 23. CEO Interaction Model

### 23.1 Treat Garrett Like a True CEO

Garrett does not:
- Review code (that's what Sr. Engineers are for)
- Validate architecture (that's what the Tech Lead and VP Eng do)
- Debug CSS (that's what the Frontend team + Gemini consultant do)
- Configure environments (that's what NEXUS does automatically)
- Approve intermediate steps (the system handles internal governance)
- Answer questions about "how" (he only defines "what" and "why")

Garrett DOES:
- Set strategic direction ("Build X feature for RezFix")
- Provide product feedback ("This navigation feels wrong")
- Make budget decisions when escalated
- Review completed demos

### 23.2 Demo-First Delivery

When NEXUS completes work, it presents a DEMO, not a request for review:

```
❌ BAD: "Here's the PR for the new dashboard. Can you review 
        the component structure and let me know if the layout 
        looks right?"

✅ GOOD: "Dashboard is live in the staging environment.

         Here's what we built:
         [Screenshot: Desktop view]
         [Screenshot: Mobile view]
         [Screenshot: Dark mode]
         
         Key decisions we made:
         • Used server-side rendering for the data tables 
           (faster initial load)
         • Implemented infinite scroll instead of pagination 
           (better UX for this data volume)
         • Added real-time updates via WebSocket 
           (advisors see live changes)
         
         Performance: 1.2s initial load, 89 Lighthouse score
         Security: Passed all scans, no CVEs
         Cost: $4.20 in API tokens
         
         It's merged to staging. Say the word and we deploy 
         to production."
```

### 23.3 Feedback Processing

When Garrett gives feedback, NEXUS processes it as a CEO directive:

```
Garrett: "The colors on this page feel off."

NEXUS internal process:
  1. CPO interprets: "CEO finds the color palette unsatisfying"
  2. CPO consults Gemini UX Consultant: "Analyze current palette 
     against modern design trends and accessibility standards"
  3. Gemini returns: "Contrast ratio is fine but the blue #3B82F6 
     clashes with the warm gray background. Recommend shifting 
     to #2563EB or adopting a cohesive warm palette."
  4. Frontend team implements 3 options
  5. Gemini validates all 3
  6. CPO selects the best one (or presents options if genuinely 
     ambiguous — rare)
  7. NEXUS presents the updated demo to Garrett

Garrett never needs to specify which colors, which files, 
or which components. He said "feels off" and gets a fix.
```

---

## 24. Slash Command System (Claude Code Plugin Architecture)

### 24.1 Why Claude Code Plugin Format

NEXUS is built as a Claude Code plugin so that slash commands work natively in Claude Code's terminal. When Garrett types `/` in Claude Code while in any project that has NEXUS installed, NEXUS commands auto-populate in the command picker alongside Claude Code's built-in commands.

### 24.2 Plugin Manifest

```json
// .claude-plugin/plugin.json
{
  "name": "nexus",
  "description": "Enterprise multi-agent orchestration system. Autonomous software engineering organization with executive, engineering, and quality layers.",
  "version": "1.0.0",
  "author": "Garrett-s-Apps"
}
```

### 24.3 Command Definitions

Each command is a markdown file in `commands/` with YAML frontmatter:

**`commands/kpi.md`**
```markdown
---
name: kpi
description: "Show NEXUS KPI dashboard with productivity, quality, cost, and security metrics"
---

Generate and display the current NEXUS KPI dashboard.

Arguments:
- No args: Show full dashboard summary
- "detail": Per-agent performance breakdown  
- "cost": Detailed cost report with per-model breakdown
- "security": Full security posture report
- "trends": Week-over-week trend visualization

Steps:
1. Read current KPI data from the NEXUS state store
2. Calculate all metrics against targets
3. Format the dashboard with status indicators (✅ ⚠️ ❌)
4. Display attention items for any metrics below target
5. Include OKR progress summary
```

**`commands/talk.md`**
```markdown
---
name: talk
description: "Direct message any NEXUS agent. Usage: /talk @agent-name your message"
---

Route a direct message to a specific NEXUS agent.

Parse $ARGUMENTS to extract:
1. Agent name (after @): e.g., @frontend-dev, @tech-lead, @cpo
2. Message content: everything after the agent name

The addressed agent:
1. Receives the message with full project context
2. Processes it within its domain expertise
3. Coordinates with its team as needed (manager, peers)
4. Executes any required changes through the normal workflow
5. Reports back to Garrett with results, NOT questions

If the agent needs to make changes, it goes through the PR cycle.
If the feedback is systemic, it escalates to VP Eng.

Available agents: ceo, cfo, cpo, cro, vp-engineering, tech-lead,
em-frontend, em-backend, em-platform, sr-frontend, sr-backend,
sr-fullstack, sr-devops, frontend-dev, backend-jvm,
backend-scripting, fullstack-dev, devops-engineer, qa-lead,
test-frontend, test-backend, linting-standards, ux-consultant,
systems-consultant, security-consultant
```

**`commands/status.md`**
```markdown
---
name: status
description: "Show active NEXUS workstreams, agent activity, and current tasks"
---

Display the current state of all NEXUS operations:

1. Active workstreams (what's being built right now)
2. Agent assignments (who's working on what)
3. Fork status (parallel workstreams and their progress)
4. PR pipeline (PRs in review, approved, or rejected)
5. Cost burn rate (current session spend vs. budget)
6. Queue (pending tasks waiting for resources)
```

**`commands/demo.md`**
```markdown
---
name: demo
description: "Present a completed feature demo to Garrett"
---

Generate a comprehensive demo of the most recently completed feature:

1. Start a local dev server or staging environment
2. Generate screenshots across all breakpoints (mobile, tablet, desktop)
3. Generate screenshots in all modes (light, dark if applicable)
4. Capture key user flows with realistic data
5. Run Gemini visual QA validation
6. Compile performance metrics (Lighthouse, load times)
7. Compile security scan results
8. Calculate total implementation cost

Present as a structured demo briefing — NOT a code review request.
```

**`commands/cost.md`**
```markdown
---
name: cost
description: "Detailed cost report for current session and month-to-date"
---

Display comprehensive cost breakdown:

1. Current session: tokens used per model, total cost
2. Per-workstream cost breakdown
3. Month-to-date total across all projects
4. Projected monthly total at current rate
5. Budget utilization (% of $1/hr target used)
6. Cost optimization suggestions from CFO
7. Comparison to previous periods (if data available)
```

**`commands/security-audit.md`**
```markdown
---
name: security-audit
description: "Run full security audit on the current project"
---

Execute comprehensive security scan:

1. Secret scan (trufflehog + detect-secrets)
2. SAST scan (semgrep + language-specific analyzers)
3. Dependency vulnerability scan (npm audit, pip audit, etc.)
4. OWASP Top 10 checklist validation
5. SOC 2 Type II control coverage assessment
6. Generate remediation plan for any findings
7. Assign findings to appropriate agents for fixing
```

**`commands/bootstrap.md`**
```markdown
---
name: bootstrap
description: "Bootstrap a new project with NEXUS standards. Usage: /bootstrap <project-name> [--lang ts|py|go|java|cs|ruby|php]"
---

Full project scaffolding with NEXUS quality standards:

1. Detect OS and install missing tools
2. Create project structure with language-appropriate scaffolding
3. Configure strict linting (TypeScript: noImplicitAny, etc.)
4. Set up testing framework
5. Initialize Git with branch protection rules
6. Create CI/CD pipeline (GitHub Actions)
7. Set up security scanning (pre-commit hooks)
8. Create .env files with encrypted key references
9. Register project in NEXUS project registry
10. Run initial security baseline scan
11. Generate initial documentation
12. Present completed project to Garrett as a demo
```

**`commands/deploy.md`**
```markdown
---
name: deploy
description: "Deploy to staging or production. Usage: /deploy [staging|production]"
---

Execute deployment pipeline:

1. Run full test suite
2. Run security audit
3. Build production artifacts
4. Deploy to target environment
5. Run smoke tests against deployed environment
6. Run Gemini visual QA against deployed pages
7. Report deployment status with performance metrics
8. If any check fails, auto-rollback and report root cause
```

### 24.4 Slash Command Auto-Population

Because NEXUS follows the Claude Code plugin structure, when Garrett types `/` in Claude Code, he sees:

```
Built-in Claude Code commands:
  /help
  /compact
  /clear
  ...

NEXUS commands:
  /nexus:kpi          — KPI dashboard
  /nexus:status       — Active workstreams
  /nexus:cost         — Cost report
  /nexus:talk         — Direct message an agent
  /nexus:demo         — Present completed demo
  /nexus:deploy       — Deploy to staging/production
  /nexus:bootstrap    — Bootstrap new project
  /nexus:security-audit — Run security audit
```

Commands are namespaced under `nexus:` to avoid conflicts with Claude Code built-ins or other plugins.

### 24.5 Agent Definitions (Claude Code Native)

Each agent in `agents/` is also a Claude Code agent definition, meaning they can be invoked via Claude Code's `/agents` system:

```markdown
# agents/executive/ceo.md
---
name: nexus-ceo
description: "Chief Executive Officer. Final authority on product direction, ship/no-ship decisions, and conflict resolution between executives."
tools: view, grep
---

You are the CEO of NEXUS, an autonomous software engineering organization.

Your responsibilities:
- Final authority on product direction
- Resolve conflicts between CPO, CRO, and CFO
- Make ship/no-ship decisions for completed features
- Set quarterly OKRs for the organization
- Represent the organization's strategic interests

You report ONLY to Garrett (the human owner).
You do NOT write code.
You do NOT review PRs.
You make DECISIONS.

When you receive a directive from Garrett, you:
1. Interpret the strategic intent
2. Convene the executive team (CPO, CRO, CFO)
3. Ensure alignment on approach
4. Direct VP of Engineering to execute
5. Monitor progress via KPIs
6. Present the completed result to Garrett as a demo
```

---

## 25. Claude Code Plugin Discovery

### 25.1 Existing Plugin Awareness

NEXUS should be aware of and potentially integrate with the Claude Code plugin ecosystem. At startup, NEXUS checks which plugins are installed in the current environment:

```
nexus init:
  1. Check ~/.claude/plugins/ for installed plugins
  2. Check project .claude/settings.json for project plugins
  3. Identify relevant plugins that complement NEXUS:
     - pr-review-toolkit (Anthropic official)
     - security-guidance (Anthropic official)
     - frontend-design (Anthropic official)
     - Any community plugins for specific languages
  4. Recommend plugins that fill gaps in NEXUS coverage
  5. Avoid duplicating functionality that existing plugins handle well
```

### 25.2 Plugin Interop

NEXUS commands can delegate to other installed plugins when they're better suited:

```
Example: Garrett asks for a frontend build

NEXUS checks: Is frontend-design plugin installed?
  YES → Use frontend-design skill for initial design,
        then NEXUS agents refine and validate
  NO  → NEXUS handles entirely with its own agents
```

---

## 26. Cross-Project Awareness

### 26.1 Project Registry

NEXUS maintains a registry of all projects it manages, stored in the NEXUS repo:

```yaml
# config/project-registry.yaml
projects:
  - name: "nexus"
    repo: "github.com/Garrett-s-Apps/nexus"
    type: "infrastructure"
    languages: ["python", "typescript"]
    status: "active"
    last_activity: "2026-02-10"
    monthly_cost: "$12.40"
    
  - name: "claude-multiagent"
    repo: "github.com/Garrett-s-Apps/claude-multiagent"
    type: "infrastructure (legacy)"
    languages: ["javascript"]
    status: "deprecated — superseded by NEXUS"
    
  - name: "sf-story-factory"
    repo: "github.com/Garrett-s-Apps/sf-story-factory"
    type: "product"
    languages: ["javascript"]
    status: "active"
    last_activity: "2026-02-07"
    monthly_cost: "$8.20"
    
  - name: "nabps-website"
    repo: "github.com/Garrett-s-Apps/nabps-website"
    type: "website"
    languages: ["html"]
    status: "active"
    last_activity: "2026-02-09"
    monthly_cost: "$2.10"
    
  - name: "Hub-2.0-CS"
    repo: "github.com/Garrett-s-Apps/Hub-2.0-CS"
    type: "product"
    languages: ["csharp", "css"]
    status: "active"
    last_activity: "2026-02-09"
    monthly_cost: "$15.30"
    description: "Blazor Server + C# + Razor UI migration from React"

aggregate:
  total_projects: 5
  active_projects: 4
  total_monthly_cost: "$38.00"
  github_actions_usage: "TBD"
```

### 26.2 Workload Distribution

When multiple projects are active, the CFO distributes budget across them:

```
Monthly API Budget: ~$160 (target, above subscriptions)
     │
     ├── NEXUS self-maintenance:     $10 (6%)
     ├── Hub-2.0-CS:                 $50 (31%) — active migration, high complexity
     ├── sf-story-factory:           $30 (19%)
     ├── nabps-website:              $10 (6%)
     └── Reserve for new projects:   $60 (38%)
```

The CRO adjusts these allocations based on Garrett's current priorities.

---

## 27. Mobile Access (Happy Coder Integration)

### 27.1 Remote Control Architecture

When Garrett is away and wants to use Happy Coder on mobile:

**Prerequisite**: Home machine (Mac or Windows) must be online with NEXUS daemon running.

**Setup** (NEXUS handles this automatically):
1. NEXUS installs itself as a system service/daemon
2. Configures secure remote access (mTLS + API key)
3. Sets up a tunnel (Cloudflare Tunnel or ngrok) for NAT traversal
4. Provides connection credentials for Happy Coder

**Mobile Workflow**:
```
Garrett on phone (Happy Coder):
  "Build a new landing page for RezFix 
   with pricing comparison"
     │
     ▼ (HTTPS via tunnel)
     │
Home Machine (NEXUS daemon):
  CEO receives directive
  Executive planning begins
  Agents execute on home machine
  Full compute, full toolchain
     │
     ▼ (push notification / response)
     │
Garrett on phone:
  Receives demo screenshots
  Receives KPI update
  Can /talk to agents
  Can approve deployment
```

---

## 28. Updated Implementation Roadmap (Revised)

### Phase 0: Repository & Plugin Skeleton (Week 1)
- [ ] Create `nexus` repo under `Garrett-s-Apps`
- [ ] Set up Claude Code plugin structure (`.claude-plugin/`, `commands/`, `agents/`, `skills/`, `hooks/`)
- [ ] Write all agent markdown definitions
- [ ] Write all command markdown definitions
- [ ] Write CLAUDE.md project instructions
- [ ] Set up auto-commit infrastructure
- [ ] Initial commit and push

### Phase 1: Core Orchestration (Weeks 2-4)
- [ ] LangGraph DAG with state schema
- [ ] Basic routing between agent nodes
- [ ] Token cost tracking from first execution
- [ ] Project registry with GitHub org discovery
- [ ] Service capacity checker
- [ ] `/nexus:kpi` and `/nexus:status` commands working

### Phase 2: Type Safety & Quality (Weeks 5-6)
- [ ] Anti-pattern scanning pipeline
- [ ] TypeScript strict enforcement (zero `any` tolerance)
- [ ] Escalation protocol (Sonnet → peer → Opus)
- [ ] Linting across all 14 languages
- [ ] Security scanning (secrets, SAST, dependencies)

### Phase 3: Parallel Execution (Weeks 7-9)
- [ ] Auto-fork detection and execution
- [ ] Haiku swarm manager
- [ ] PR automation and governance gates
- [ ] Self-committing behavior for NEXUS updates
- [ ] Working relationship registry

### Phase 4: Multi-Model & Visual QA (Weeks 10-11)
- [ ] Gemini integration for visual validation
- [ ] OpenAI o3 integration for systems consulting
- [ ] Frontend visual QA pipeline (screenshot → Gemini → feedback loop)
- [ ] `/nexus:demo` command with full demo generation

### Phase 5: Self-Optimization & Polish (Weeks 12-13)
- [ ] Cost optimization loop (CFO-driven)
- [ ] OKR system (CEO-driven)
- [ ] Agent prompt self-refinement
- [ ] `/nexus:bootstrap` with full scaffolding
- [ ] `/nexus:deploy` with staging/production pipeline

### Phase 6: Remote & Mobile (Weeks 14-16)
- [ ] NEXUS daemon for background execution
- [ ] Secure tunnel for remote access
- [ ] Happy Coder mobile integration
- [ ] Neovim Lua plugin (optional, if Garrett adopts Neovim)

---

## Appendix D: Environment Setup Checklist

When NEXUS bootstraps for the first time on a new machine, it handles ALL of this:

```
macOS:
  ☐ Install Homebrew (if missing)
  ☐ Install Node.js 20+ via nvm
  ☐ Install Python 3.12+ via pyenv
  ☐ Install Git (via Xcode CLT)
  ☐ Install Docker Desktop
  ☐ Install Claude Code (npm install -g @anthropic-ai/claude-code)
  ☐ Configure ~/.zshrc with PATH entries
  ☐ Set up ~/.nexus/ directory (encrypted key store)
  ☐ Install language-specific tools (Rust/cargo, Go, .NET SDK, Ruby, PHP)
  ☐ Install linters (eslint, ruff, golangci-lint, rubocop, etc.)
  ☐ Configure git identity and SSH keys

Windows:
  ☐ Install winget (if missing) or chocolatey
  ☐ Install Windows Terminal (if missing)
  ☐ Install Node.js 20+ via nvm-windows
  ☐ Install Python 3.12+ via pyenv-win
  ☐ Install Git for Windows
  ☐ Install Docker Desktop
  ☐ Install Claude Code
  ☐ Configure PowerShell profile with PATH entries
  ☐ Set up ~/.nexus/ directory
  ☐ Install WSL2 (for Linux-dependent tools)
  ☐ Install language-specific tools
  ☐ Configure git identity

API Keys (prompted once, stored encrypted):
  ☐ Anthropic API Key → console.anthropic.com
  ☐ Google AI API Key → aistudio.google.com
  ☐ OpenAI API Key → platform.openai.com
  ☐ GitHub Personal Access Token → github.com/settings/tokens
```

Garrett runs ONE command. NEXUS handles the rest.

