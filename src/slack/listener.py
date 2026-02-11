"""
NEXUS Slack Listener

Listens for messages in #garrett-nexus and forwards everything to the
daemon's /message endpoint. The CEO interpreter figures out whether
it's a directive, question, org change, or command.

No command parsing here — natural language only.
"""

import os
import re
import asyncio
import aiohttp
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

DAEMON_URL = "http://127.0.0.1:4200"


def _load_key(key_name: str) -> str | None:
    val = os.environ.get(key_name)
    if val:
        return val
    try:
        with open(os.path.expanduser("~/.nexus/.env.keys")) as f:
            for line in f:
                line = line.strip()
                if line.startswith(key_name + "="):
                    return line.split("=", 1)[1]
    except FileNotFoundError:
        pass
    return None


async def send_to_daemon(message: str) -> dict:
    async with aiohttp.ClientSession() as session:
        try:
            if message.startswith("/talk"):
                match = re.match(r"/talk\s+@?(\S+)\s+(.*)", message, re.DOTALL)
                if match:
                    async with session.post(
                        f"{DAEMON_URL}/talk",
                        json={
                            "agent_name": match.group(1),
                            "message": match.group(2),
                            "source": "slack",
                        },
                    ) as resp:
                        return await resp.json()

            async with session.post(
                f"{DAEMON_URL}/message",
                json={
                    "message": message,
                    "source": "slack",
                },
            ) as resp:
                return await resp.json()

        except aiohttp.ClientError as e:
            return {"error": f"Cannot reach NEXUS daemon: {e}"}


async def start_slack_listener():
    app_token = _load_key("SLACK_APP_TOKEN")
    bot_token = _load_key("SLACK_BOT_TOKEN")
    channel_id = _load_key("SLACK_CHANNEL")

    if not app_token or not bot_token:
        print("ERROR: Missing SLACK_APP_TOKEN or SLACK_BOT_TOKEN in ~/.nexus/.env.keys")
        return

    web_client = AsyncWebClient(token=bot_token)
    socket_client = SocketModeClient(
        app_token=app_token,
        web_client=web_client,
    )

    async def handle_event(client: SocketModeClient, req: SocketModeRequest):
        await client.send_socket_mode_response(
            SocketModeResponse(envelope_id=req.envelope_id)
        )

        if req.type != "events_api":
            return

        event = req.payload.get("event", {})

        if event.get("type") != "message":
            return
        if event.get("bot_id"):
            return
        if event.get("channel") != channel_id:
            return

        text = event.get("text", "").strip()
        if not text:
            return

        result = await send_to_daemon(text)

        if result.get("error"):
            await web_client.chat_postMessage(
                channel=channel_id,
                text=f"Error: {result['error']}",
            )
        elif result.get("category") == "QUESTION":
            pass
        elif result.get("category") == "ORG_CHANGE":
            pass
        elif "response" in result:
            await web_client.chat_postMessage(
                channel=channel_id,
                text=f"*{result.get('agent', 'Agent')}*: {result.get('response', '')[:2000]}",
            )

    socket_client.socket_mode_request_listeners.append(handle_event)

    print("NEXUS Slack listener starting...")
    await socket_client.connect()

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(start_slack_listener())
