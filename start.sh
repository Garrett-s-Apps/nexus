#!/bin/bash
# NEXUS Start Script — boots engine + Cloudflare tunnel for remote access.
#
# Usage:
#   ./start.sh          # engine + tunnel
#   ./start.sh local    # engine only (no tunnel)
#
# The tunnel URL will be printed — paste it into the dashboard settings gear.

set -e
cd "$(dirname "$0")"

cleanup() {
  echo ""
  echo "[NEXUS] Shutting down..."
  kill $ENGINE_PID 2>/dev/null || true
  kill $TUNNEL_PID 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

# Start the engine
echo "[NEXUS] Starting engine on 0.0.0.0:4200..."
python3 -m src.main &
ENGINE_PID=$!

# Wait for engine to be ready
for i in $(seq 1 30); do
  if curl -s http://localhost:4200/health > /dev/null 2>&1; then
    echo "[NEXUS] Engine is ready."
    break
  fi
  sleep 1
done

if [ "$1" = "local" ]; then
  echo ""
  echo "╔══════════════════════════════════════════════════════╗"
  echo "║  NEXUS running locally                              ║"
  echo "║  Dashboard: http://localhost:4200/dashboard          ║"
  echo "║  Passphrase: (from ~/.nexus/.env.keys)              ║"
  echo "╚══════════════════════════════════════════════════════╝"
  wait $ENGINE_PID
  exit 0
fi

# Check for cloudflared
if ! command -v cloudflared &> /dev/null; then
  echo "[NEXUS] cloudflared not found. Install: brew install cloudflare/cloudflare/cloudflared"
  echo "[NEXUS] Running in local-only mode."
  wait $ENGINE_PID
  exit 0
fi

# Start tunnel
echo "[NEXUS] Starting Cloudflare tunnel..."
TUNNEL_LOG=$(mktemp)
cloudflared tunnel --url http://localhost:4200 2>"$TUNNEL_LOG" &
TUNNEL_PID=$!

# Extract the tunnel URL
TUNNEL_URL=""
for i in $(seq 1 15); do
  TUNNEL_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1)
  if [ -n "$TUNNEL_URL" ]; then
    break
  fi
  sleep 1
done
rm -f "$TUNNEL_LOG"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  NEXUS is live!                                            ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Local:   http://localhost:4200/dashboard                  ║"
if [ -n "$TUNNEL_URL" ]; then
echo "║  Remote:  $TUNNEL_URL  ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Paste the remote URL into the dashboard settings gear     ║"
echo "║  on your Vercel deployment to connect remotely.            ║"
fi
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

wait $ENGINE_PID
