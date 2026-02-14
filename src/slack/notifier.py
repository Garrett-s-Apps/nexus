"""
NEXUS Slack Notifier

Sends notifications to the #garrett-nexus Slack channel.
Tags @Garrett Eaglin on all substantive messages by default.
"""

import logging

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.config import get_key

logger = logging.getLogger("nexus.slack.notifier")

_owner_user_id: str | None = None


def get_client():
    token = get_key("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not configured")
    return WebClient(token=token)


def get_channel():
    return get_key("SLACK_CHANNEL") or "nexus"


def _get_owner_user_id() -> str | None:
    """Resolve Garrett's Slack user ID for @mentions."""
    global _owner_user_id
    if _owner_user_id is not None:
        return _owner_user_id

    # Check config first
    configured = get_key("SLACK_OWNER_USER_ID")
    if configured:
        _owner_user_id = configured
        return _owner_user_id

    # Look up by name via Slack API
    try:
        client = get_client()
        result = client.users_list()
        for member in result.get("members", []):
            profile = member.get("profile", {})
            real_name = profile.get("real_name", "").lower()
            if "garrett" in real_name and "eaglin" in real_name:
                _owner_user_id = member["id"]
                logger.info("Resolved owner Slack ID: %s", _owner_user_id)
                return _owner_user_id
    except SlackApiError:
        pass

    return None


def notify(message, blocks=None, thread_ts=None, tag_owner=True):
    """Send a Slack notification. Tags @Garrett by default.

    Set tag_owner=False for processing/status messages that don't need a ping.
    """
    client = get_client()
    channel = get_channel()
    try:
        client.conversations_join(channel=channel)
    except SlackApiError:
        pass

    # Tag Garrett on substantive messages
    owner_id = _get_owner_user_id() if tag_owner else None
    if owner_id:
        message = f"<@{owner_id}> {message}"

    try:
        kwargs = {"channel": channel, "text": message}
        if blocks:
            kwargs["blocks"] = blocks
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        client.chat_postMessage(**kwargs)
    except SlackApiError as e:
        logger.error("Slack notification failed: %s", e.response['error'])


def notify_demo(project, summary, screenshots=None, metrics=None):
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Demo Ready: {project}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
    ]
    if metrics:
        blocks.append({
            "type": "section",
            "fields": [{"type": "mrkdwn", "text": f"*{k}*\n{v}"} for k, v in metrics.items()]
        })
    blocks.append({
        "type": "actions",
        "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Deploy to Production"}, "action_id": "deploy_prod", "style": "primary"},
            {"type": "button", "text": {"type": "plain_text", "text": "View KPIs"}, "action_id": "view_kpis"},
        ]
    })
    notify(f"Demo ready: {project}", blocks=blocks)


def notify_kpi(dashboard_text):
    notify(f"```{dashboard_text}```")


def notify_escalation(agent, reason):
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "Escalation Required"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*From:* {agent}\n*Reason:* {reason}"}},
    ]
    notify(f"Escalation from {agent}: {reason}", blocks=blocks)


def notify_cost_alert(current_rate, budget):
    notify(f"Cost alert: Current burn rate ${current_rate:.2f}/hr exceeds target ${budget:.2f}/hr. Switching to efficiency mode.")


def notify_completion(project, feature, cost):
    notify(f"Feature complete: *{feature}* on {project}. Total cost: ${cost:.2f}")


def send_approval_request(title: str, context: dict, approval_id: str) -> dict:
    """Send Slack message with interactive approve/reject buttons using Block Kit.

    Args:
        title: Approval request title
        context: Context dictionary with description, requester, severity, etc.
        approval_id: Unique approval identifier for state tracking

    Returns:
        Response from Slack API
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🔔 Approval Required: {title}"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": context.get("description", "")}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Requester:* {context.get('requester', 'Unknown')}"},
                {"type": "mrkdwn", "text": f"*Severity:* {context.get('severity', 'Normal')}"},
            ]
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve"},
                    "style": "primary",
                    "value": f"{approval_id}:approve",
                    "action_id": "approval_approve"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Reject"},
                    "style": "danger",
                    "value": f"{approval_id}:reject",
                    "action_id": "approval_reject"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "💬 Request Changes"},
                    "value": f"{approval_id}:changes",
                    "action_id": "approval_changes"
                }
            ]
        }
    ]

    client = get_client()
    channel = get_channel()
    try:
        client.conversations_join(channel=channel)
    except SlackApiError:
        pass

    try:
        result = client.chat_postMessage(channel=channel, blocks=blocks, text=title)
        logger.info("Approval request sent: %s", approval_id)
        return result
    except SlackApiError as e:
        logger.error("Failed to send approval request: %s", e.response['error'])
        raise
