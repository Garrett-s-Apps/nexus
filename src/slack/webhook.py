"""
NEXUS Slack Webhook Handler

Handles interactive button clicks and actions from Slack messages.
Integrates with LangGraph state to drive approval workflows.
"""

import json
import logging
import hmac
import hashlib
import time
from typing import Optional

from flask import Flask, request, jsonify

logger = logging.getLogger("nexus.slack.webhook")


class SlackWebhookHandler:
    """Handles Slack interactive components and updates approval state."""

    def __init__(self, signing_secret: str):
        """Initialize webhook handler with Slack signing secret.

        Args:
            signing_secret: SLACK_SIGNING_SECRET for request verification
        """
        self.signing_secret = signing_secret
        self.approval_states = {}  # In-memory approval state tracker

    def verify_slack_request(self, timestamp: str, signature: str, body: str) -> bool:
        """Verify that the request came from Slack using signature verification.

        Args:
            timestamp: X-Slack-Request-Timestamp header
            signature: X-Slack-Signature header
            body: Raw request body

        Returns:
            True if request is valid, False otherwise
        """
        # Check timestamp to prevent replay attacks
        current_time = int(time.time())
        request_time = int(timestamp)
        if abs(current_time - request_time) > 300:  # 5 minutes
            logger.warning("Request timestamp too old: %d vs current %d", request_time, current_time)
            return False

        # Verify signature
        base_string = f"v0:{timestamp}:{body}".encode()
        my_signature = "v0=" + hmac.new(
            self.signing_secret.encode(),
            base_string,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(my_signature, signature)

    def handle_interactive_action(self, payload: dict) -> tuple[int, dict]:
        """Handle interactive button clicks and actions.

        Args:
            payload: Slack interactive payload

        Returns:
            Tuple of (status_code, response_dict)
        """
        try:
            # Extract action information
            action = payload.get("actions", [{}])[0]
            action_id = action.get("action_id")
            value = action.get("value", "")

            if not value or ":" not in value:
                logger.error("Invalid action value format: %s", value)
                return 400, {"text": "Invalid action format"}

            approval_id, decision = value.split(":", 1)

            # Log the action
            logger.info("Approval action: %s -> %s", approval_id, decision)

            # Store approval decision in state
            self.approval_states[approval_id] = {
                "decision": decision,
                "timestamp": int(time.time()),
                "user_id": payload.get("user", {}).get("id"),
                "team_id": payload.get("team", {}).get("id"),
            }

            # Return confirmation message
            response_text = self._get_confirmation_message(decision, approval_id)
            return 200, {"text": response_text}

        except Exception as e:
            logger.error("Error handling interactive action: %s", e)
            return 500, {"text": "Internal server error"}

    def _get_confirmation_message(self, decision: str, approval_id: str) -> str:
        """Generate user-friendly confirmation message.

        Args:
            decision: The decision made (approve, reject, changes)
            approval_id: The approval ID

        Returns:
            Confirmation message text
        """
        decision_map = {
            "approve": "✅ Approved",
            "reject": "❌ Rejected",
            "changes": "💬 Changes Requested",
        }
        return f"{decision_map.get(decision, 'Decision recorded')}: {approval_id}"

    def get_approval_decision(self, approval_id: str) -> Optional[dict]:
        """Retrieve an approval decision from state.

        Args:
            approval_id: The approval ID to look up

        Returns:
            Decision dict with decision, timestamp, user_id, or None if not found
        """
        return self.approval_states.get(approval_id)

    def clear_approval_state(self, approval_id: str) -> None:
        """Clear an approval decision from state.

        Args:
            approval_id: The approval ID to clear
        """
        if approval_id in self.approval_states:
            del self.approval_states[approval_id]
            logger.info("Cleared approval state: %s", approval_id)


def create_webhook_app(signing_secret: str) -> Flask:
    """Create Flask app for handling Slack webhooks.

    Args:
        signing_secret: SLACK_SIGNING_SECRET for request verification

    Returns:
        Flask application instance
    """
    app = Flask(__name__)
    handler = SlackWebhookHandler(signing_secret)

    @app.route("/slack/interactive", methods=["POST"])
    def handle_interactive():
        """Handle interactive button clicks from Slack."""
        # Verify request came from Slack
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")
        body = request.get_data(as_text=True)

        if not handler.verify_slack_request(timestamp, signature, body):
            logger.warning("Invalid Slack request signature")
            return jsonify({"error": "Unauthorized"}), 401

        # Parse payload
        try:
            payload = json.loads(request.form.get("payload", "{}"))
        except json.JSONDecodeError:
            logger.error("Invalid JSON in payload")
            return jsonify({"error": "Bad payload"}), 400

        # Handle the action
        status_code, response = handler.handle_interactive_action(payload)

        return jsonify(response), status_code

    @app.route("/slack/approval-status/<approval_id>", methods=["GET"])
    def get_approval_status(approval_id: str):
        """Query the status of an approval.

        Args:
            approval_id: The approval ID to check

        Returns:
            JSON response with approval status or 404 if not found
        """
        decision = handler.get_approval_decision(approval_id)
        if decision is None:
            return jsonify({"status": "pending"}), 200
        return jsonify({"status": "completed", **decision}), 200

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok"}), 200

    # Store handler as app context for access by graph
    app.slack_handler = handler

    return app
