# NEXUS Organization Chart

_Auto-generated from live registry at 2026-02-11 07:50:05_

## Reporting Structure

```
GARRETT (Human CEO)
  Sets direction, reviews demos, gives feedback
  │
  CEO [opus]
    Chief Product Officer [opus]
      UX Consultant [gemini]
    Chief Financial Officer [opus]
      Cost Optimization Consultant [haiku]
    Chief Revenue Officer [opus]
    VP of Engineering [opus]
      Tech Lead [opus]
      Engineering Manager - Frontend [sonnet]
        Senior Frontend Engineer [sonnet]
        Frontend Developer [sonnet]
      Engineering Manager - Backend [sonnet]
        Senior Backend Engineer [sonnet]
        Senior Full-Stack Engineer [sonnet]
        Backend Developer - JVM/Systems [sonnet]
        Backend Developer - Scripting [sonnet]
        Full-Stack Developer [sonnet]
        Performance Engineer [sonnet]
      Engineering Manager - Platform [sonnet]
        Senior DevOps Engineer [sonnet]
        DevOps Engineer [sonnet]
      QA Lead [sonnet]
        Test Engineer - Frontend [sonnet]
        Test Engineer - Backend [sonnet]
        Linting & Standards Agent [haiku]
      Security Consultant [opus]
      Systems Architecture Consultant [o3]
```

## Agents by Layer

### Executive Layer

| Agent | ID | Model | Reports To | Status |
|-------|----|-------|------------|--------|
| CEO | `ceo` | anthropic/opus | Garrett | active |
| Chief Product Officer | `cpo` | anthropic/opus | CEO | active |
| Chief Financial Officer | `cfo` | anthropic/opus | CEO | active |
| Chief Revenue Officer | `cro` | anthropic/opus | CEO | active |

### Management Layer

| Agent | ID | Model | Reports To | Status |
|-------|----|-------|------------|--------|
| VP of Engineering | `vp_engineering` | anthropic/opus | CEO | active |
| Tech Lead | `tech_lead` | anthropic/opus | VP of Engineering | active |
| Engineering Manager - Frontend | `em_frontend` | anthropic/sonnet | VP of Engineering | active |
| Engineering Manager - Backend | `em_backend` | anthropic/sonnet | VP of Engineering | active |
| Engineering Manager - Platform | `em_platform` | anthropic/sonnet | VP of Engineering | active |

### Senior Layer

| Agent | ID | Model | Reports To | Status |
|-------|----|-------|------------|--------|
| Senior Frontend Engineer | `sr_frontend` | anthropic/sonnet | Engineering Manager - Frontend | active |
| Senior Backend Engineer | `sr_backend` | anthropic/sonnet | Engineering Manager - Backend | active |
| Senior Full-Stack Engineer | `sr_fullstack` | anthropic/sonnet | Engineering Manager - Backend | active |
| Senior DevOps Engineer | `sr_devops` | anthropic/sonnet | Engineering Manager - Platform | active |

### Implementation Layer

| Agent | ID | Model | Reports To | Status |
|-------|----|-------|------------|--------|
| Frontend Developer | `frontend_dev` | anthropic/sonnet | Engineering Manager - Frontend | active |
| Backend Developer - JVM/Systems | `backend_jvm` | anthropic/sonnet | Engineering Manager - Backend | active |
| Backend Developer - Scripting | `backend_scripting` | anthropic/sonnet | Engineering Manager - Backend | active |
| Full-Stack Developer | `fullstack_dev` | anthropic/sonnet | Engineering Manager - Backend | active |
| DevOps Engineer | `devops_engineer` | anthropic/sonnet | Engineering Manager - Platform | active |
| Performance Engineer | `perf_engineer` | anthropic/sonnet | Engineering Manager - Backend | active |

### Quality Layer

| Agent | ID | Model | Reports To | Status |
|-------|----|-------|------------|--------|
| QA Lead | `qa_lead` | anthropic/sonnet | VP of Engineering | active |
| Test Engineer - Frontend | `test_frontend` | anthropic/sonnet | QA Lead | active |
| Test Engineer - Backend | `test_backend` | anthropic/sonnet | QA Lead | active |
| Linting & Standards Agent | `linting_agent` | anthropic/haiku | QA Lead | active |

### Consultant Layer

| Agent | ID | Model | Reports To | Status |
|-------|----|-------|------------|--------|
| Security Consultant | `security_consultant` | anthropic/opus | VP of Engineering | active |
| UX Consultant | `ux_consultant` | google/gemini | Chief Product Officer | active |
| Systems Architecture Consultant | `systems_consultant` | openai/o3 | VP of Engineering | active |
| Cost Optimization Consultant | `cost_consultant` | anthropic/haiku | Chief Financial Officer | active |

## Summary

| Metric | Value |
|--------|-------|
| Total Active Agents | 27 |
| Executive Layer | 4 |
| Management Layer | 5 |
| Senior Layer | 4 |
| Implementation Layer | 6 |
| Quality Layer | 4 |
| Consultant Layer | 4 |

## Model Distribution

| Provider/Model | Agent Count |
|---------------|-------------|
| anthropic/haiku | 2 |
| anthropic/opus | 7 |
| anthropic/sonnet | 16 |
| google/gemini | 1 |
| openai/o3 | 1 |

## Recent Org Changes

| Time | Action | Agent | Details |
|------|--------|-------|--------|
| 2026-02-11 01:02 | hired | perf_engineer | Hired Performance Engineer (sonnet) in implementation layer, reports to em_backe |
| 2026-02-10 23:48 | initialized | None | Loaded initial org from agents.yaml |
