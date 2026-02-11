import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

KEYS_PATH = os.path.expanduser("~/.nexus/.env.keys")

def _load_keys():
    keys = {}
    try:
        with open(KEYS_PATH) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    keys[k] = v
    except FileNotFoundError:
        pass
    return keys

def get_client():
    keys = _load_keys()
    return WebClient(token=keys["SLACK_BOT_TOKEN"])

def get_channel():
    keys = _load_keys()
    return keys.get("SLACK_CHANNEL", "nexus")

def notify(message, blocks=None):
    client = get_client()
    channel = get_channel()
    try:
        client.conversations_join(channel=channel)
    except SlackApiError:
        pass
    try:
        client.chat_postMessage(channel=channel, text=message, blocks=blocks)
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
