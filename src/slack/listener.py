"""
NEXUS Slack Listener

Listens for messages in #garrett-nexus and forwards everything to the
server's /message endpoint. Sends ALL responses back to Slack.
"""

import os
import re
import asyncio
import aiohttp
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

SERVER_URL = "http://127.0.0.1:4200"


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


def format_response(result: dict) -> str:
    """Turn a server response into a readable Slack message."""
    category = result.get("category", "")

    if category == "ORG_CHANGE":
        return f"*Org Change:* {result.get('summary', '')}\n\n{result.get('result', '')}"

    elif category == "QUESTION":
        return f"*Q:* {result.get('summary', '')}\n\n{result.get('answer', 'No answer available.')}"

    elif category == "COMMAND":
        if "dashboard" in result:
            return f"```{result['dashboard']}```"
        elif "total_cost" in result:
            lines = [
                f"*Cost Report*",
                f"Total: ${result['total_cost']:.2f}",
                f"Hourly: ${result['hourly_rate']:.2f}/hr",
                f"Over budget: {result.get('over_budget', False)}",
            ]
            return "\n".join(lines)
        elif "summary" in result:
            return result["summary"]
        elif "reporting_tree" in result:
            return f"*Current Org:*\n```{result['reporting_tree']}```"
        elif "chart" in result:
            return f"```{result['chart'][:3000]}```"
        else:
            return f"```{str(result)[:2000]}```"

    elif category == "DIRECTIVE":
        return f"*Directive received:* {result.get('summary', '')}\n{result.get('message', 'Working on it...')}"

    elif "response" in result:
        return f"*{result.get('agent', 'Agent')}*: {result['response'][:2000]}"

    elif "error" in result:
        return f"Error: {result['error']}"

    return f"```{str(result)[:2000]}```"


async def send_to_server(message: str) -> dict:
    """Send a message to the server and return the response."""
    async with aiohttp.ClientSession() as session:
        try:
            if message.startswith("/talk"):
                match = re.match(r"/talk\s+@?(\S+)\s+(.*)", message, re.DOTALL)
                if match:
                    async with session.post(
                        f"{SERVER_URL}/talk",
                        json={
                            "agent_name": match.group(1),
                            "message": match.group(2),
                            "source": "slack",
                        },
                    ) as resp:
                        return await resp.json()

            async with session.post(
                f"{SERVER_URL}/message",
                json={
                    "message": message,
                    "source": "slack",
                },
            ) as resp:
                return await resp.json()

        except aiohttp.ClientError as e:
            return {"error": f"Cannot reach NEXUS server: {e}"}


async def start_slack_listener():
    """Start the Slack Socket Mode listener."""
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
        # Acknowledge immediately so Slack doesn't retry
        await client.send_socket_mode_response(
            SocketModeResponse(envelope_id=req.envelope_id)
        )

        if req.type != "events_api":
            return

        event = req.payload.get("event", {})

        # Only handle messages, not bot messages, only in our channel
        if event.get("type") != "message":
            return
        if event.get("bot_id"):
            return
        if event.get("channel") != channel_id:
            return

        text = event.get("text", "").strip()
        if not text:
            return

        print(f"[Slack] Received: {text[:100]}")

        # Check if this is a document request
        from src.documents.generator import detect_doc_request, generate_document

        doc_info = detect_doc_request(text)
        if doc_info:
            print(f"[Slack] Document request detected: {doc_info['format']}")
            try:
                await web_client.chat_postMessage(
                    channel=channel_id,
                    text=f"Generating your {doc_info['format'].upper()}... one moment.",
                )

                doc_result = await generate_document(text, doc_info)

                if "error" in doc_result:
                    await web_client.chat_postMessage(
                        channel=channel_id,
                        text=f"Error generating document: {doc_result['error']}",
                    )
                else:
                    await web_client.files_upload_v2(
                        channel=channel_id,
                        file=doc_result["filepath"],
                        title=doc_result["title"],
                        initial_comment=f"Here's your {doc_result['format'].upper()}: *{doc_result['title']}*",
                    )
                    print(f"[Slack] Uploaded: {doc_result['filename']}")
            except Exception as e:
                print(f"[Slack] Document generation failed: {e}")
                await web_client.chat_postMessage(
                    channel=channel_id,
                    text=f"Failed to generate document: {str(e)[:200]}",
                )
            return

        # Send to server for normal processing
        result = await send_to_server(text)

        # Format and send response back to Slack
        response_text = format_response(result)

        print(f"[Slack] Responding: {response_text[:100]}...")

        try:
            await web_client.chat_postMessage(
                channel=channel_id,
                text=response_text,
            )
        except Exception as e:
            print(f"[Slack] Failed to send response: {e}")

    socket_client.socket_mode_request_listeners.append(handle_event)

    print("NEXUS Slack listener starting...")
    await socket_client.connect()
    print("NEXUS Slack listener connected.")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(start_slack_listener())
