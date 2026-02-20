#!/bin/bash
# NEXUS CLI Sandbox Entrypoint
#
# Runs Claude CLI in pipe mode with stream-json output.
# Prompt is passed via stdin (pipe mode) or as first argument.
# API keys come from environment variables.
# No wall-clock timeout — stall detection is handled by the Python pool.

set -euo pipefail

# Verify API key is available
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo '{"type":"result","subtype":"error","error":"ANTHROPIC_API_KEY not set"}' >&2
    exit 1
fi

# Model selection (default: opus)
MODEL="${NEXUS_CLI_MODEL:-opus}"

AUTONOMOUS_PROMPT="You are a fully autonomous agent. NEVER ask the user questions or pause for confirmation. Make all decisions independently and complete the task fully without check-ins or interactive prompts. If something is unclear, make a reasonable assumption and continue. Tasks may run for hours or days — keep working until fully done."

# Build CLI args
CLI_ARGS=(
    "--model" "$MODEL"
    "-p"
    "--verbose"
    "--output-format" "stream-json"
    "--dangerously-skip-permissions"
    "--append-system-prompt" "$AUTONOMOUS_PROMPT"
)

# If arguments provided, pass as prompt; otherwise read from stdin
if [ $# -gt 0 ]; then
    echo "$*" | claude "${CLI_ARGS[@]}"
else
    claude "${CLI_ARGS[@]}"
fi
