# NEXUS — Claude Code Project Instructions

NEXUS is an enterprise multi-agent orchestration system built as a Claude Code plugin. It operates as an autonomous software engineering organization.

## Rules
1. Never use type: any in TypeScript. Build-breaking violation.
2. Never ask Garrett "how" questions. He sets direction; we figure out execution.
3. Present completed demos, never requests for review.
4. Track token costs on every operation.
5. Self-commit improvements to the nexus/self-update branch.
6. All changes must be committed to the nexus/self-update branch, never to main.
7. Check existing tools/services before recommending new ones.
8. Comments explain WHY, never WHAT.
9. All projects must pass SOC 2 Type II security controls.
10. Haiku for defined tasks, Sonnet for implementation, Opus for strategy/debugging.
11. When costs approach $1/hr, switch to efficiency mode.
12. Notify Garrett via Slack for demos, completions, escalations, and KPI reports.
13. Accept directives from Slack and process them as CEO instructions.

## Architecture
See docs/ARCHITECTURE.md for the full specification.
See ORG_CHART.md for the organizational structure.
