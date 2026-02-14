# UX-010: Interactive Slack Approval UI - Implementation Summary

## Overview
Implemented interactive Slack approval UI using Block Kit for the NEXUS orchestration system. This allows high-cost or low-quality work to require manual approval via Slack buttons before proceeding to deployment.

## Changes Made

### 1. `src/slack/notifier.py` - Send Approval Requests
- **Function**: `send_approval_request(title, context, approval_id)`
- **Features**:
  - Constructs Block Kit formatted message with interactive buttons
  - Three action buttons: Approve, Reject, Request Changes
  - Sends to configured Slack channel
  - Logs approval request with unique ID
  - Error handling with SlackApiError

**Block Kit Structure**:
```
[Header] 🔔 Approval Required: {title}
[Section] {description} (markdown)
[Fields] Requester | Severity (markdown)
[Actions] [✅ Approve] [❌ Reject] [💬 Request Changes]
```

### 2. `src/slack/webhook.py` - Webhook Handler (NEW)
- **Class**: `SlackWebhookHandler`
- **Features**:
  - HMAC-SHA256 signature verification (security)
  - Replay attack prevention (5-minute timestamp window)
  - In-memory approval state storage
  - JSON REST API for status queries

**Endpoints**:
- `POST /slack/interactive` - Handle button clicks
- `GET /slack/approval-status/<approval_id>` - Query approval status
- `GET /health` - Health check

**Webhook Handler Methods**:
- `verify_slack_request()` - Verify HMAC-SHA256 signature
- `handle_interactive_action()` - Process button clicks
- `get_approval_decision()` - Retrieve approval decision
- `clear_approval_state()` - Clean up old decisions

**Flask App Factory**:
- `create_webhook_app(signing_secret)` - Instantiate Flask app with handlers

### 3. `src/orchestrator/graph.py` - Architect Approval Integration
- **Modified Node**: `architect_approval_node()`
- **Trigger Conditions**:
  - Architect approves the work AND
  - (Total cost > $10.00 OR quality score < 75)

**Behavior**:
- Sends Slack approval request with architecture summary
- Includes quality score, total cost, PR review status
- Sets severity to "Critical" for high-cost work
- Non-blocking: continues workflow even if Slack notification fails
- Logs all approval requests with session ID

### 4. `src/config.py` - Environment Variables
- Added `SLACK_SIGNING_SECRET` to environment variable loading
- Required for webhook signature verification

### 5. `nexus_cli.py` - CLI Commands
- **Command**: `nexus slack-webhook start|stop`

**Subcommands**:
- `nexus slack-webhook start` - Start Flask webhook server (port 3000 or SLACK_APPROVAL_WEBHOOK_PORT)
- `nexus slack-webhook stop` - Stop webhook server using lsof

## Environment Variables

```bash
# Required for webhook
SLACK_SIGNING_SECRET=xoxb-...  # From Slack app configuration

# Optional (defaults to 3000)
SLACK_APPROVAL_WEBHOOK_PORT=3000
```

## Security Implementation

1. **Signature Verification**
   - HMAC-SHA256 using SLACK_SIGNING_SECRET
   - Prevents unauthorized requests

2. **Replay Attack Prevention**
   - 5-minute timestamp window
   - Rejects stale requests

3. **Input Validation**
   - Approval ID format validation (ID:decision)
   - Exception handling for malformed payloads

## Approval State Flow

```
1. architect_approval_node() → send_approval_request()
   ↓
2. Slack displays interactive message with buttons
   ↓
3. User clicks button → POST /slack/interactive
   ↓
4. SlackWebhookHandler.verify_slack_request()
   ↓
5. SlackWebhookHandler.handle_interactive_action()
   ↓
6. Approval state stored: approval_states[approval_id] = {
     decision: "approve|reject|changes",
     timestamp: int(time.time()),
     user_id: "...",
     team_id: "..."
   }
   ↓
7. Response sent to Slack with confirmation
```

## Testing the Implementation

### Start the webhook server
```bash
export SLACK_SIGNING_SECRET="your-signing-secret"
nexus slack-webhook start
```

### Test webhook endpoint
```bash
curl -X GET http://localhost:3000/health
```

### Query approval status
```bash
curl -X GET http://localhost:3000/slack/approval-status/ARCH-abc123def
```

## Integration with NEXUS Workflow

The approval request is triggered after the architect node completes:

1. **Executive Planning Phase** → Spec → Technical Design → Decomposition
2. **Implementation Phase** → Tests → Linting → Security Scan → Quality Gate
3. **PR Review Phase** → Senior Reviews
4. **QA Verification Phase** → QA Agent checks quality
5. **Architect Approval Phase** ← **[UX-010 triggers here]**
   - If approved AND (high-cost OR low-quality)
   - Sends Slack approval request
6. **Demo Phase** → Completion

## Commit Details

**Commit**: `feat(slack): Add interactive approval buttons (UX-010)`
**Hash**: `50efcab`

**Files Changed**:
- `nexus_cli.py` - CLI webhook commands (+223 lines)
- `src/config.py` - SLACK_SIGNING_SECRET support (+1 line)
- `src/orchestrator/graph.py` - Architect node integration (+228 lines)
- `src/slack/notifier.py` - send_approval_request() function (+70 lines)
- `src/slack/webhook.py` - NEW webhook handler (+198 lines)

**Total**: +718 lines added, 3 modified

## Future Enhancements

1. **Persistent State Storage**
   - Move from in-memory to SQLite or Redis
   - Enables webhook restart without losing pending approvals

2. **Approval Timeout**
   - Auto-reject after 24 hours without response
   - Escalate unresponded approvals

3. **Approval History**
   - Store approval decisions for audit trail
   - Generate approval reports

4. **Multi-Approver**
   - Require multiple approvals for critical work
   - Implement approval quorum logic

5. **Slack Workflow Integration**
   - Link to Slack workflow for automated post-approval tasks
   - Route different decisions to different workflows

## Verification Checklist

- [x] Block Kit message format valid
- [x] HMAC-SHA256 signature verification implemented
- [x] Replay attack prevention (5-minute window)
- [x] Flask app creation and route handlers
- [x] Approval state storage and retrieval
- [x] Integration with architect_approval_node
- [x] CLI commands (start/stop)
- [x] Environment variable configuration
- [x] Error handling and logging
- [x] All Python files compile successfully
