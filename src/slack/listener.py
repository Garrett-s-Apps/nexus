import os
import re
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

def parse_command(text):
    text = text.strip()
    if text.startswith("/kpi"):
        return {"command": "kpi", "args": text[4:].strip()}
    if text.startswith("/status"):
        return {"command": "status", "args": text[7:].strip()}
    if text.startswith("/cost"):
        return {"command": "cost", "args": text[5:].strip()}
    if text.startswith("/talk"):
        match = re.match(r"/talk\s+@(\S+)\s+(.*)", text, re.DOTALL)
        if match:
            return {"command": "talk", "agent": match.group(1), "message": match.group(2)}
    if text.startswith("/deploy"):
        return {"command": "deploy", "args": text[7:].strip() or "staging"}
    if text.startswith("/security-audit"):
        return {"command": "security_audit", "args": text[15:].strip()}
    return {"command": "directive", "message": text}

def start_listener(command_handler):
    app_token = os.environ.get("SLACK_APP_TOKEN")
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    if not app_token:
        with open(os.path.expanduser("~/.nexus/.env.keys")) as f:
            for line in f:
                if line.startswith("SLACK_APP_TOKEN="):
                    app_token = line.strip().split("=", 1)[1]
                if line.startswith("SLACK_BOT_TOKEN="):
                    bot_token = line.strip().split("=", 1)[1]

    client = SocketModeClient(
        app_token=app_token,
        web_client=WebClient(token=bot_token)
    )

    def handle(client, req):
        if req.type == "events_api":
            event = req.payload.get("event", {})
            if event.get("type") == "message" and not event.get("bot_id"):
                text = event.get("text", "")
                parsed = parse_command(text)
                command_handler(parsed, event.get("channel"))
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

    client.socket_mode_request_listeners.append(handle)
    client.connect()
