#!/bin/bash
# Nexus Environment Setup for Rebuild Branch

# Load existing keys
source ~/.nexus/.env.keys

# Generate NEXUS_MASTER_SECRET if not already set
if [ -z "$NEXUS_MASTER_SECRET" ]; then
    echo "Generating NEXUS_MASTER_SECRET (256-bit)..."
    NEXUS_MASTER_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "NEXUS_MASTER_SECRET=$NEXUS_MASTER_SECRET" >> ~/.nexus/.env.keys
fi

# Export all required variables
export ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY"
export GOOGLE_AI_API_KEY="$GOOGLE_AI_API_KEY"
export OPENAI_API_KEY="$OPENAI_API_KEY"
export GITHUB_TOKEN="$GITHUB_TOKEN"
export SLACK_CHANNEL="$SLACK_CHANNEL"
export SLACK_BOT_TOKEN="$SLACK_BOT_TOKEN"
export SLACK_APP_TOKEN="$SLACK_APP_TOKEN"
export NEXUS_DASHBOARD_KEY="$NEXUS_DASHBOARD_KEY"
export VERCEL_TOKEN="$VERCEL_TOKEN"
export NEXUS_MASTER_SECRET="$NEXUS_MASTER_SECRET"

echo "✅ Environment variables set!"
echo ""
echo "Required variables for Nexus rebuild:"
echo "  NEXUS_MASTER_SECRET: ${NEXUS_MASTER_SECRET:0:20}..."
echo "  NEXUS_DASHBOARD_KEY: ${NEXUS_DASHBOARD_KEY}"
echo "  ANTHROPIC_API_KEY:   ${ANTHROPIC_API_KEY:0:20}..."
echo ""
echo "To use these in your shell:"
echo "  source setup_env.sh"
