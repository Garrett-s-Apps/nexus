# NEXUS — Claude Code Project Instructions

NEXUS is an enterprise multi-agent orchestration system built as a Claude Code plugin. It operates as an autonomous software engineering organization.

## Commands

```bash
# Start server (engine + Cloudflare tunnel)
./start.sh              # full: engine + tunnel
./start.sh local        # engine only, no tunnel
python3 -m src.main     # engine directly

# Quality checks
ruff check src/         # lint (must pass before commit)
mypy src/               # type check
pytest tests/           # run test suite
```

## Environment

- Python >= 3.11
- Keys file: `~/.nexus/.env.keys` (loaded by `src/config.py`)
- Required keys: `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_CHANNEL`, `SLACK_OWNER_USER_ID`
- Optional keys: `OPENAI_API_KEY`, `GOOGLE_API_KEY`
- Databases: `~/.nexus/*.db` (memory, cost, kpi, sessions, knowledge — SQLite)
- Server: `http://localhost:4200` (dashboard at `/dashboard`, health at `/health`)

## Directory Structure

```
src/
  agents/       # Agent registry, org chart, conversation, base classes
  config.py     # Central config — keys, paths, constants
  cost/         # Token cost tracking per model/agent/project
  documents/    # Document generation (docx, pptx, xlsx)
  main.py       # Entry point: python -m src.main
  ml/           # ML system — embeddings, predictor, similarity, feedback
  observability/# Structured logging, metrics, background tasks
  orchestrator/ # Task runner, executor, planning pipeline
  server/       # FastAPI server, auth, health checks
  sessions/     # CLI session pool (Docker-isolated)
  slack/        # Slack listener + notifier
  security/     # Auth gate, JWT, security scanning
docker/
  cli-sandbox/  # Dockerfile + entrypoint for isolated CLI sessions
tests/          # pytest suite (18 test modules)
```

## Rules
1. Never use type: any in TypeScript. Build-breaking violation.
2. CLI sessions ALWAYS run in Docker (`nexus-cli-sandbox`), never native.
3. Never ask Garrett "how" questions. He sets direction; we figure out execution.
4. Present completed demos, never requests for review.
5. Track token costs on every operation.
6. All changes committed to `nexus/self-update` branch, never `main`.
7. Check existing tools/services before recommending new ones.
8. Comments explain WHY, never WHAT.
9. All projects must pass SOC 2 Type II security controls.
10. Haiku for defined tasks, Sonnet for implementation, Opus for strategy/debugging.
11. When costs approach $1/hr, switch to efficiency mode.
12. Notify Garrett via Slack for demos, completions, escalations, and KPI reports.
13. Accept directives from Slack and process them as CEO instructions.

## Gotchas

- `zip()` calls require `strict=` parameter (ruff B905)
- Use typed intermediate variables for serialized returns (`mypy`)
- Use `_db` property pattern for optional `Connection` fields
- `ruff check` ignores: S101, E501, E701, E702, E731, S608, S603, S110, E402, SIM105, SIM108, SIM117

## Architecture
See docs/ARCHITECTURE.md for the full specification.
See ORG_CHART.md for the organizational structure.
