#!/bin/bash
# NEXUS CLI Sandbox Entrypoint
#
# Runs Claude CLI in pipe mode with stream-json output.
# Prompt is passed via stdin (pipe mode) or as first argument.
# API keys come from environment variables.

set -euo pipefail

# Verify API key is available
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo '{"type":"result","subtype":"error","error":"ANTHROPIC_API_KEY not set"}' >&2
    exit 1
fi

# Model selection (default: opus)
MODEL="${NEXUS_CLI_MODEL:-opus}"
TIMEOUT="${NEXUS_CLI_TIMEOUT:-900}"

# Build CLI args
CLI_ARGS=(
    "--dangerously-skip-permissions"
    "--model" "$MODEL"
    "-p"
    "--verbose"
    "--output-format" "stream-json"
)

# If arguments provided, pass as prompt; otherwise read from stdin
if [ $# -gt 0 ]; then
    echo "$*" | timeout "$TIMEOUT" claude "${CLI_ARGS[@]}"
else
    timeout "$TIMEOUT" claude "${CLI_ARGS[@]}"
fi
