# NEXUS

**Enterprise Multi-Agent Orchestration System**

A 26-agent autonomous software engineering organization controlled entirely through natural language. Tell it what to build. It figures out the rest.

## Architecture

```
You (CEO)
  └─ Slack / Neovim / CLI / API
       └─ NEXUS Server (localhost:4200)
            ├─ CEO Interpreter (Opus) — classifies your intent
            ├─ Agent Registry (SQLite) — dynamic org management
            ├─ LangGraph Orchestrator — routes work through the org
            ├─ Agent SDK Bridge — executes code via Claude Agent SDK
            └─ Multi-Model — Anthropic, Google, OpenAI
```

## The Organization

| Layer | Agents | Model |
|-------|--------|-------|
| Executive | CEO, CPO, CFO, CRO | Opus |
| Management | VP Eng, Tech Lead, 3 EMs | Opus/Sonnet |
| Senior | 4 Senior Engineers | Sonnet |
| Implementation | 5 Developers | Sonnet |
| Quality | QA Lead, 2 Test Eng, Linting | Sonnet/Haiku |
| Consultants | Security (Opus), UX (Gemini), Systems (o3), Cost (Haiku) | Mixed |

All agents are dynamically managed. Hire, fire, promote, reassign — all through natural language.

## Quick Start

```bash
# Clone
git clone https://github.com/Garrett-s-Apps/nexus.git
cd nexus

# Set up Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure API keys
mkdir -p ~/.nexus
cat > ~/.nexus/.env.keys << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_AI_API_KEY=AIza...
OPENAI_API_KEY=sk-proj-...
GITHUB_TOKEN=ghp_...
SLACK_CHANNEL=C0...
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
EOF
chmod 600 ~/.nexus/.env.keys

# Start
python -m src.main
```

## Usage

### Slack (Primary Interface)

Send messages in your configured Slack channel:

```
Build me a landing page for RezFix
What's our current org structure?
Hire a performance engineer, Sonnet, reports to EM Backend
Fire the frontend dev and have fullstack cover it
Create a pitch deck for investor meetings
What's our burn rate?
```

### Neovim

```vim
:Nexus Build a new API endpoint for user authentication
:NexusTalk tech_lead What's the best approach for caching?
:NexusOrg
:NexusStatus
:NexusKpi
```

Keymaps: `<leader>nx` prompt, `<leader>no` org, `<leader>ns` status

### CLI

```bash
python nexus_cli.py status
python nexus_cli.py talk tech_lead "Review the auth module"
python nexus_cli.py message "Deploy to staging"
```

### API

```bash
curl -X POST http://127.0.0.1:4200/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me the org", "source": "api"}'
```

## Document Generation

Ask for any document and NEXUS generates and uploads it to Slack:

```
Create a pitch deck for RezFix showing problem, solution, and market size
Write a PDF report on our Q1 engineering metrics
Generate a Word doc outlining the 90-day roadmap for The Prompt Fixer
```

Supports: `.docx`, `.pptx`, `.pdf`

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/status` | GET | Active sessions, cost, agent count |
| `/message` | POST | Universal input — CEO interpreter routes everything |
| `/talk` | POST | Direct conversation with specific agent |
| `/org` | GET | Full org summary and reporting tree |
| `/org/chart` | GET | Generated org chart markdown |
| `/kpi` | GET | KPI dashboard |
| `/sessions` | GET | Recent session history |
| `/session/{id}` | GET | Session detail with messages |

## Auto-Start (macOS)

```bash
bash install_service.sh
```

NEXUS starts on login, restarts on crash. Logs at `~/.nexus/logs/`.

## Tech Stack

- **Orchestration**: LangGraph + Claude Agent SDK
- **Server**: FastAPI + Uvicorn
- **Persistence**: SQLite (registry, sessions, KPIs)
- **Communication**: Slack Socket Mode
- **Models**: Claude Opus/Sonnet/Haiku, Gemini, OpenAI o3
- **IDE**: Neovim Lua plugin (extensible to any IDE)

## License

Private — Garrett-s-Apps
