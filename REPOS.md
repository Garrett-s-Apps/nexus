# NEXUS Ecosystem - Repository Structure

The NEXUS project has been split into three separate repositories:

## 1. nexus (Main Server)
**Location:** `/Users/garretteaglin/Projects/nexus`
**GitHub:** https://github.com/eaglin/nexus

**Purpose:** FastAPI server with multi-agent orchestration

**Key Features:**
- 26-agent engineering organization
- Slack integration
- Cost tracking and KPI monitoring
- CLI session pooling (Docker)
- Memory and knowledge management

**New in nexus/self-update:**
- Provider abstraction layer (src/agents/provider_factory.py)
- Dual-path execution (SDK + legacy support)
- Environment-based model configuration
- Feature flag: NEXUS_USE_SDK_PROVIDERS

**Installation:**
```bash
cd /Users/garretteaglin/Projects/nexus
./start.sh
```

---

## 2. nexus-sdk (Python Package)
**Location:** `/Users/garretteaglin/Projects/nexus-sdk`
**GitHub:** https://github.com/eaglin/nexus-sdk (to be created)
**PyPI:** nexus-agent-sdk (to be published)

**Purpose:** Standalone SDK for multi-agent orchestration

**Key Features:**
- Provider-agnostic (Claude, OpenAI, Gemini, local)
- Cost tracking with budget enforcement
- Agent registry and orchestration
- Diverse agent names (balanced representation)
- Zero dependencies for core
- Optional extras per provider

**Installation:**
```bash
pip install nexus-agent-sdk[claude]
```

**Usage:**
```python
from nexus_sdk import AgentRegistry, get_agent_name
from nexus_sdk.providers.claude import ClaudeProvider

provider = ClaudeProvider(api_key="...")
registry = AgentRegistry(provider=provider)
agent_info = get_agent_name("senior_engineer")
agent = registry.register(id="eng", name=agent_info["name"], role="Engineer", model="sonnet")
result = await agent.execute("Build feature X")
```

---

## 3. nexus-plugin (Claude Code Plugin)
**Location:** `/Users/garretteaglin/Projects/nexus-plugin`
**GitHub:** https://github.com/eaglin/nexus-plugin (to be created)

**Purpose:** Claude Code marketplace plugin

**Key Features:**
- 3 auto-triggered skills
- 4 specialized agents
- 3 slash commands
- Autonomous execution
- Zero cost (uses Claude Code subscription)

**Installation:**
```bash
claude install https://github.com/eaglin/nexus-plugin
```

**Skills:**
- autonomous-build: Full feature development
- code-review-org: Multi-perspective review
- cost-report: Budget tracking

**Commands:**
- /nexus-status: Org status
- /nexus-cost: Cost report
- /nexus-hire: Add agent

---

## Repository Relationships

```
nexus (server)
├── Uses nexus-sdk (optional, via feature flag)
└── Connects to nexus-plugin (plugin calls server at localhost:4200)

nexus-sdk (standalone)
└── Used by anyone building AI agent systems

nexus-plugin (standalone)
└── Can work with or without nexus server
```

---

## Next Steps

### For nexus repo:
```bash
cd /Users/garretteaglin/Projects/nexus
git push origin nexus/self-update
# Create PR to merge server refactoring
```

### For nexus-sdk repo:
```bash
cd /Users/garretteaglin/Projects/nexus-sdk
gh repo create eaglin/nexus-sdk --public --source=. --remote=origin
git push -u origin main
# Then publish to PyPI (see docs/PUBLISHING.md)
```

### For nexus-plugin repo:
```bash
cd /Users/garretteaglin/Projects/nexus-plugin
gh repo create eaglin/nexus-plugin --public --source=. --remote=origin
git push -u origin main
# Then submit to Claude Code marketplace
```

---

## Documentation

- **nexus:** See main README.md, docs/ARCHITECTURE.md
- **nexus-sdk:** See README.md, examples/, QUICKSTART.md
- **nexus-plugin:** See README.md

---

## Commits Summary

**nexus/self-update:**
- 1 commit: Server refactoring (provider abstraction)

**nexus-sdk:**
- 1 commit: Initial SDK (3,380 lines, 34 files)

**nexus-plugin:**
- 1 commit: Initial plugin (881 lines, 12 files)

**Total new code:** 4,261 lines across 2 new repos
