# NEXUS Organization Chart

```
                            ┌─────────────────┐
                            │     GARRETT      │
                            │   (Human CEO)    │
                            │                  │
                            │  Sets direction  │
                            │  Reviews demos   │
                            │  Gives feedback  │
                            └────────┬─────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    CEO (Opus)    │    │   CFO (Sonnet)  │    │   CRO (Sonnet)  │
│                  │    │                  │    │                  │
│ Product direction│    │ Token budget     │    │ Delivery velocity│
│ Ship decisions   │    │ Cost tracking    │    │ Throughput       │
│ Conflict resolve │    │ ROI analysis     │    │ Bottleneck ID    │
└────────┬─────────┘    └─────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐
│   CPO (Opus)    │
│                  │
│ Requirements     │
│ UX validation    │
│ Real-person test │
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VP OF ENGINEERING (Opus)                       │
│              Translates strategy → technical execution            │
│                   Owns architecture governance                    │
└──────┬──────────────────────┬──────────────────────┬─────────────┘
       │                      │                      │
       ▼                      ▼                      ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  EM Frontend │    │  EM Backend  │    │  EM Platform │
│  (Sonnet)    │    │  (Sonnet)    │    │  (Sonnet)    │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
  ┌────┴────┐         ┌────┴────┐         ┌────┴────┐
  ▼         ▼         ▼         ▼         ▼         ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│Sr FE │ │FE Dev│ │Sr BE │ │BE Dev│ │Sr DO │ │DO Eng│
│Sonnet│ │Sonnet│ │Sonnet│ │Sonnet│ │Sonnet│ │Sonnet│
└──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘
                     │
              ┌──────┴──────┐
              ▼             ▼
         ┌──────┐     ┌──────┐
         │BE JVM│     │BE Scr│
         │Sonnet│     │Sonnet│
         │Java  │     │Py/Rb │
         │Go/C# │     │PHP   │
         └──────┘     └──────┘


┌─────────────────────────────────────────────────────────────────┐
│                      TECH LEAD (Opus)                            │
│          Deepest technical authority. Debugging escalation.       │
│               Final call on architectural disputes.              │
└─────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│                     QUALITY ASSURANCE                             │
│                                                                   │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ QA Lead  │  │ Test FE   │  │ Test BE   │  │ Lint/Stds    │  │
│  │ (Sonnet) │  │ (Sonnet)  │  │ (Sonnet)  │  │ (Haiku)      │  │
│  └──────────┘  └───────────┘  └───────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│                     CONSULTANT POOL                               │
│                    (On-demand specialists)                         │
│                                                                   │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ UX        │  │ Systems   │  │ Security  │  │ Cost Optim.  │ │
│  │ (Gemini)  │  │ (o3)      │  │ (Opus)    │  │ (Haiku)      │ │
│  │ Visual QA │  │ Algo/Perf │  │ Threats   │  │ Efficiency   │ │
│  └───────────┘  └───────────┘  └───────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│                      HAIKU SWARM                                  │
│              (Cheap, fast, parallelizable workers)                │
│                                                                   │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │
│  │Code    │ │Test    │ │Lint    │ │Doc     │ │Format  │       │
│  │Writers │ │Writers │ │Runners │ │Updaters│ │ters    │       │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘       │
│  ┌────────┐ ┌────────┐                                          │
│  │File    │ │Migra-  │                                          │
│  │Scanners│ │tors    │                                          │
│  └────────┘ └────────┘                                          │
└─────────────────────────────────────────────────────────────────┘
```

## Agent Count Summary

| Layer              | Count | Model(s)        | Cost Share |
|--------------------|-------|-----------------|------------|
| Executive          | 4     | Opus + Sonnet   | ~15%       |
| Engineering Mgmt   | 5     | Opus + Sonnet   | ~10%       |
| Senior Engineers   | 4     | Sonnet          | ~15%       |
| Implementation     | 5     | Sonnet          | ~25%       |
| Quality Assurance  | 4     | Sonnet + Haiku  | ~15%       |
| Consultants        | 4     | Mixed providers | ~10%       |
| Haiku Swarm        | N     | Haiku           | ~10%       |
| **Total**          | **26+ agents** | | |

## Model Distribution

| Provider   | Model       | Agents | Role |
|-----------|-------------|--------|------|
| Anthropic | Opus 4.6    | 5      | CEO, CPO, VP Eng, Tech Lead, Security |
| Anthropic | Sonnet 4.5  | 17     | Engineering, management, QA |
| Anthropic | Haiku 4.5   | N      | Swarm tasks, linting, doc updates |
| Google    | Gemini 2.0  | 1      | UX/Visual QA |
| OpenAI    | o3          | 1      | Systems Architecture |

## Reporting Lines

```
Garrett → CEO → CPO → VP Eng → Eng Managers → Sr. Engineers → Developers
                CFO → Cost Optimization Consultant
                CRO → (monitors all layers for throughput)
                VP Eng → Tech Lead (dotted line, technical authority)
                VP Eng → QA Lead → Test Engineers + Linting Agent
```

## Direct Access

Garrett can `/talk @agent-name` to any Sonnet or Opus agent directly. That agent coordinates with its team. Garrett never manages the workflow.
