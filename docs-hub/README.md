# NEXUS Documentation Hub

This directory contains the comprehensive documentation website for buildwithnexus.dev - a complete hub covering everything about the NEXUS enterprise multi-agent orchestration system.

## Structure

```
docs-hub/
├── pages/
│   ├── index.md              # Landing page
│   ├── overview/             # System overview and architecture
│   ├── comparisons/          # vs OpenClaw, Devin, Codex, Claude Code
│   ├── plugin/               # Claude Code plugin documentation
│   ├── sdk/                  # Python SDK documentation
│   ├── use-cases/            # Walkthroughs and tutorials
│   ├── security/             # Security posture and compliance
│   └── api/                  # API reference
├── assets/                   # Images, diagrams, videos
├── components/               # Reusable documentation components
├── public/                   # Static assets
├── package.json              # Next.js configuration
├── next.config.js            # Build configuration
└── vercel.json               # Vercel deployment config
```

## Deployment

This documentation hub is deployed to buildwithnexus.dev via Vercel, automatically building from the `docs/buildwithnexus-hub` branch.