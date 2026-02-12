"""
NEXUS Slack Notifier

Sends notifications to the #garrett-nexus Slack channel.
"""

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.config import get_key


def get_client():
    token = get_key("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not configured")
    return WebClient(token=token)


def get_channel():
    return get_key("SLACK_CHANNEL") or "nexus"


def notify(message, blocks=None, thread_ts=None):
    client = get_client()
    channel = get_channel()
    try:
        client.conversations_join(channel=channel)
    except SlackApiError:
        pass
    try:
        kwargs = {"channel": channel, "text": message}
        if blocks:
            kwargs["blocks"] = blocks
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        client.chat_postMessage(**kwargs)
    except SlackApiError as e:
        print(f"Slack notification failed: {e.response['error']}")


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
