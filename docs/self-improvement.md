# Nexus Self-Improvement System (ARCH-015)

## Overview

Nexus can analyze and improve its own codebase through an automated feedback loop. This enables continuous quality improvement without manual intervention.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Self-Improvement Loop                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Self-Analysis                                            │
│     ├─ Run AnalyzerAgent on Nexus codebase                  │
│     ├─ Generate findings (SEC, PERF, CODE, MAINT)           │
│     └─ Save to .claude/self-analysis-state.json             │
│                                                               │
│  2. Auto-Fix (LOW/MEDIUM severity)                           │
│     ├─ Filter XS/S effort items                             │
│     ├─ Apply fixes via appropriate agents                   │
│     └─ Track success/failure metrics                        │
│                                                               │
│  3. PR Creation (HIGH/CRITICAL severity)                     │
│     ├─ Group findings by category                           │
│     ├─ Create feature branches                              │
│     ├─ Apply fixes                                          │
│     └─ Create PRs for human review                          │
│                                                               │
│  4. Metrics & Learning                                       │
│     ├─ Track improvement trends                             │
│     ├─ Analyze failure patterns                             │
│     └─ Update agent prompts with learnings                  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. SelfImprovementLoop (`src/self_improvement/analyzer.py`)

Main orchestrator for self-improvement.

**Methods:**
- `run_self_analysis()` - Analyze Nexus codebase
- `auto_fix_issues(max_severity)` - Auto-fix LOW/MEDIUM issues
- `create_pr_for_high_severity()` - Create PRs for HIGH/CRITICAL issues

### 2. ImprovementMetrics (`src/self_improvement/metrics.py`)

Tracks improvement trends over time.

**Methods:**
- `record_analysis(findings, summary)` - Record analysis results
- `get_trend()` - Get improvement trend data
- `get_latest_analysis()` - Get most recent analysis

**Storage:** `~/.nexus/self_improvement_metrics.json`

### 3. FailurePatternAnalyzer (`src/self_improvement/learner.py`)

Learns from failures and improves agent prompts.

**Methods:**
- `analyze_failure_patterns(days_back)` - Analyze failure patterns
- Identifies common errors, problematic agents, task types
- Generates actionable recommendations

### 4. PromptUpdater (`src/self_improvement/prompt_updater.py`)

Updates agent system prompts based on learnings.

**Methods:**
- `update_agent_prompt(agent_key, learnings)` - Update specific agent
- `add_learning_to_all_agents(learning)` - Update all agents
- `get_agent_learnings(agent_key)` - Retrieve agent learnings

## CLI Commands

### Self-Analysis

```bash
nexus self-analyze
```

Runs analysis on the Nexus codebase and generates findings across:
- **SEC**: Security vulnerabilities
- **PERF**: Performance bottlenecks
- **CODE**: Code quality issues
- **MAINT**: Maintainability concerns

Output saved to `.claude/self-analysis-state.json`

### Auto-Fix

```bash
nexus self-fix
```

Automatically fixes LOW and MEDIUM severity issues with XS/S effort estimates.

**Behavior:**
- Filters to auto-fixable items
- Applies fixes via appropriate agents
- Tracks success/failure
- Reports results

### Create PRs

```bash
nexus self-pr
```

Creates pull requests for HIGH and CRITICAL severity issues.

**Behavior:**
- Groups findings by category
- Creates feature branches (e.g., `self-improve/sec-20260214`)
- Applies fixes
- Generates PR with detailed description
- Returns to original branch

### View Metrics

```bash
nexus self-metrics
```

Shows self-improvement trend over time.

**Displays:**
- Total analyses
- Findings change over time
- Improvement status (✅ IMPROVING or ⚠️ NEEDS ATTENTION)
- Latest analysis summary

## Usage Patterns

### Weekly Self-Improvement Cycle

```bash
# Monday: Run analysis
nexus self-analyze

# View findings and metrics
nexus self-metrics

# Auto-fix simple issues
nexus self-fix

# Create PRs for complex issues
nexus self-pr

# Review PRs, merge improvements
# Repeat weekly
```

### Automated Cron Job

```cron
# Weekly self-analysis (Sunday midnight)
0 0 * * 0 cd /path/to/nexus && nexus self-analyze

# Daily auto-fix (3 AM)
0 3 * * * cd /path/to/nexus && nexus self-fix
```

### CI/CD Integration

```yaml
# .github/workflows/self-improvement.yml
name: Self-Improvement

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  workflow_dispatch:

jobs:
  self-improve:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run Self-Analysis
        run: nexus self-analyze

      - name: Auto-Fix Issues
        run: nexus self-fix

      - name: Create PRs
        run: nexus self-pr
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Metrics Schema

### `~/.nexus/self_improvement_metrics.json`

```json
{
  "version": "1.0",
  "created_at": "2026-02-14T12:00:00Z",
  "analyses": [
    {
      "timestamp": "2026-02-14T12:00:00Z",
      "total_findings": 42,
      "by_severity": {
        "CRITICAL": 2,
        "HIGH": 5,
        "MEDIUM": 15,
        "LOW": 20
      },
      "by_category": {
        "SEC": 8,
        "PERF": 10,
        "CODE": 12,
        "MAINT": 12
      },
      "total_effort_hours": 120,
      "estimated_work_days": 15.0,
      "findings_by_effort": {
        "XS": 10,
        "S": 12,
        "M": 15,
        "L": 5,
        "XL": 0
      }
    }
  ]
}
```

## Learning & Adaptation

### Failure Pattern Analysis

The system analyzes failures from `memory.db` to identify:
- **Timeout errors** → Increase timeout limits
- **Import/dependency errors** → Review dependency management
- **Type errors** → Improve type checking
- **Permission errors** → Review access controls

### Prompt Evolution

Agent prompts are updated with learnings:

```yaml
# config/agents.yaml (after learning)
agents:
  - key: code_reviewer
    system_prompt: |
      You are a code reviewer...

      ## Learnings from Self-Improvement
      - [2026-02-14] Always check for SQL injection in user inputs
      - [2026-02-13] Verify error handling in async functions
      - [2026-02-12] Ensure type hints for all public APIs
```

## Integration with Rebuild Workflow

Self-improvement findings can feed into the rebuild workflow:

```bash
# 1. Self-analyze
nexus self-analyze

# 2. Generate rebuild report
nexus generate-report .claude/self-analysis-state.json nexus-self-improvement.docx

# 3. Execute findings as rebuild tasks
nexus execute-priority CRITICAL
```

## Best Practices

1. **Run analysis weekly** to catch quality drift early
2. **Review PRs carefully** - auto-fixes may need human verification
3. **Monitor metrics** to ensure continuous improvement
4. **Update prompts** based on recurring failures
5. **Integrate with CI/CD** for automated quality gates

## Security Considerations

- Self-analysis runs in read-only mode
- Auto-fixes limited to LOW/MEDIUM severity
- HIGH/CRITICAL require human approval via PRs
- All changes tracked in git history
- Metrics stored locally (no external reporting)

## Future Enhancements

- [ ] Integration with GitHub API for automated PR creation
- [ ] ML-based fix recommendation
- [ ] Cross-project learning (learn from other codebases)
- [ ] A/B testing of prompt improvements
- [ ] Automated rollback on failed fixes
