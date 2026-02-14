# NEXUS CLI Sandbox — isolated Claude Code execution environment
#
# Bakes in Claude CLI + dev dependencies so CLI sessions run sandboxed.
# Target project directory is mounted at runtime (never baked in).
#
# Build:  docker build -t nexus-cli-sandbox docker/cli-sandbox/
# Run:    docker run --rm -v /path/to/project:/workspace \
#           -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
#           nexus-cli-sandbox "your prompt here"

FROM node:22-alpine

# System dependencies for Claude CLI and common dev workflows
RUN apk add --no-cache \
    python3 py3-pip \
    git curl wget jq \
    build-base \
    bash coreutils

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code@latest

# Install common dev tools agents might need
RUN npm install -g typescript tsx prettier eslint

# Create non-root user for sandboxed execution
RUN adduser -D -s /bin/bash nexus \
    && mkdir -p /workspace /home/nexus/.claude \
    && chown -R nexus:nexus /workspace /home/nexus

# Pre-accept Claude CLI permissions (skip interactive prompts)
RUN echo '{"hasCompletedOnboarding":true,"primaryApiKey":"env"}' \
    > /home/nexus/.claude/settings.json \
    && chown nexus:nexus /home/nexus/.claude/settings.json

USER nexus
WORKDIR /workspace

# Entrypoint: run Claude CLI in pipe mode with stream-json output
COPY --chown=nexus:nexus entrypoint.sh /home/nexus/entrypoint.sh
RUN chmod +x /home/nexus/entrypoint.sh

ENTRYPOINT ["/home/nexus/entrypoint.sh"]
