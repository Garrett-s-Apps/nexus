#!/bin/bash
# NEXUS macOS Service Installer
# Installs NEXUS as a launchd service that starts on login
#
# Usage: bash install_service.sh

set -e

PLIST_NAME="com.nexus.server"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
NEXUS_DIR="$HOME/Projects/nexus"
VENV_PYTHON="$NEXUS_DIR/.venv/bin/python"
LOG_DIR="$HOME/.nexus/logs"

mkdir -p "$LOG_DIR"

# Get SSL cert path
SSL_CERT_FILE=$($VENV_PYTHON -c "import certifi; print(certifi.where())" 2>/dev/null || echo "")

cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>

    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>-m</string>
        <string>src.main</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$NEXUS_DIR</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:$HOME/.npm-global/bin</string>
        <key>HOME</key>
        <string>$HOME</string>
        <key>SSL_CERT_FILE</key>
        <string>$SSL_CERT_FILE</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/nexus.log</string>

    <key>StandardErrorPath</key>
    <string>$LOG_DIR/nexus.error.log</string>

    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
PLIST

echo "Installed: $PLIST_PATH"

# Unload if already loaded
launchctl unload "$PLIST_PATH" 2>/dev/null || true

# Load the service
launchctl load "$PLIST_PATH"

echo ""
echo "NEXUS service installed and started."
echo ""
echo "Commands:"
echo "  Start:   launchctl load $PLIST_PATH"
echo "  Stop:    launchctl unload $PLIST_PATH"
echo "  Status:  curl -s http://127.0.0.1:4200/health"
echo "  Logs:    tail -f $LOG_DIR/nexus.log"
echo "  Errors:  tail -f $LOG_DIR/nexus.error.log"
echo ""
echo "NEXUS will auto-start on login."
