"""
NEXUS Slack Listener

Listens for messages in #garrett-nexus and forwards everything to the
server's /message endpoint. Sends ALL responses back to Slack.

Features:
- Instant Haiku acknowledgment (<5 seconds)
- Document generation and upload
- Error logging with context
"""

import os
import re
import asyncio
import traceback
import aiohttp
import anthropic
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


# ============================================
# INSTANT ACKNOWLEDGMENT (Haiku)
# ============================================

async def get_instant_ack(message: str) -> str:
    """Use Haiku to instantly acknowledge the message and confirm understanding."""
    try:
        api_key = _load_key("ANTHROPIC_API_KEY")
        if not api_key:
            return f"Got it — working on: {message[:80]}"

        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            system=(
                "You are NEXUS, an AI engineering org's quick-response system. "
                "The CEO just sent a message. In 1-2 SHORT sentences, acknowledge what they're asking for. "
                "Be specific about what you understood. If the request is ambiguous, ask ONE clarifying question. "
                "Use a confident, professional tone. No emojis. No fluff. No markdown formatting — plain text only."
            ),
            messages=[{"role": "user", "content": message}],
        )
        return response.content[0].text
    except Exception as e:
        print(f"[Slack] Haiku ack failed: {e}")
        return f"Got it — working on: {message[:80]}"


# ============================================
# RESPONSE FORMATTING
# ============================================

def md_to_slack(text: str) -> str:
    """Convert markdown formatting to Slack mrkdwn formatting."""
    import re

    # Headers → bold text
    text = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)

    # Bold: **text** or __text__ → *text*
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    text = re.sub(r'__(.+?)__', r'*\1*', text)

    # Italic: *text* (single) is already Slack bold, so skip
    # _text_ → _text_ (same in Slack)

    # Links: [text](url) → <url|text>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<\2|\1>', text)

    # Inline code: `code` stays the same in Slack

    # Code blocks: ```lang\n...\n``` → ```\n...\n```
    text = re.sub(r'```\w*\n', '```\n', text)

    # Bullet lists: - item or * item → •  item
    text = re.sub(r'^[\-\*]\s+', '•  ', text, flags=re.MULTILINE)

    # Numbered lists: keep as-is, Slack handles them fine

    # Horizontal rules: --- or *** → ———
    text = re.sub(r'^[\-\*]{3,}$', '———', text, flags=re.MULTILINE)

    # Clean up double bold from conversion: **text** → *text* might leave ***
    text = text.replace('***', '*')

    return text.strip()


def format_response(result: dict) -> str:
    """Turn a server response into a readable Slack message."""
    if "error" in result:
        return f"*Error:* {result['error']}"

    category = result.get("category", "")

    if category == "ORG_CHANGE":
        summary = md_to_slack(result.get('summary', ''))
        body = md_to_slack(result.get('result', ''))
        return f"*Org Change:* {summary}\n\n{body}"

    elif category == "QUESTION":
        summary = md_to_slack(result.get('summary', ''))
        answer = md_to_slack(result.get('answer', 'No answer available.'))
        return f"*Q:* {summary}\n\n{answer}"

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
            if result.get("monthly_cost"):
                lines.append(f"Month-to-date: ${result['monthly_cost']:.2f}")
            return "\n".join(lines)
        elif "summary" in result and isinstance(result["summary"], str):
            if result.get("reporting_tree"):
                return f"*Current Org:*\n```{result['reporting_tree']}```"
            return md_to_slack(result["summary"])
        elif "reporting_tree" in result:
            return f"*Current Org:*\n```{result['reporting_tree']}```"
        elif "chart" in result:
            return f"```{result['chart'][:3000]}```"
        else:
            return f"```{str(result)[:2000]}```"

    elif category == "CONVERSATION":
        return result.get('answer', '')

    elif category == "DIRECTIVE":
        summary = md_to_slack(result.get('summary', ''))
        msg = md_to_slack(result.get('message', 'Working on it...'))
        return f"*Directive received:* {summary}\n{msg}"

    elif "response" in result:
        agent = result.get('agent', 'Agent')
        body = md_to_slack(result['response'][:2000])
        return f"*{agent}:* {body}"

    return f"```{str(result)[:2000]}```"


# ============================================
# CONVERSATION HISTORY
# ============================================

# In-memory rolling history (last 20 messages)
conversation_history: list[dict] = []
MAX_HISTORY = 20


def add_to_history(role: str, content: str):
    """Add a message to conversation history."""
    conversation_history.append({"role": role, "content": content})
    if len(conversation_history) > MAX_HISTORY:
        conversation_history.pop(0)


def get_history_for_api() -> list[dict]:
    """Get history formatted for the Anthropic messages API."""
    return list(conversation_history)


# ============================================
# SERVER COMMUNICATION
# ============================================

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
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            return {"error": f"Server returned {resp.status}: {text[:200]}"}
                        return await resp.json()

            async with session.post(
                f"{SERVER_URL}/message",
                json={
                    "message": message,
                    "source": "slack",
                    "history": get_history_for_api(),
                },
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"error": f"Server returned {resp.status}: {text[:200]}"}
                return await resp.json()

        except aiohttp.ClientError as e:
            return {"error": f"Cannot reach NEXUS server: {type(e).__name__}: {e}"}
        except asyncio.TimeoutError:
            return {"error": "Request timed out after 120 seconds. The server may still be processing."}
        except Exception as e:
            return {"error": f"Unexpected error: {type(e).__name__}: {e}"}


# ============================================
# MAIN LISTENER
# ============================================

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

        # Track user message in history
        add_to_history("user", text)

        try:
            # Check if this is a document request first
            from src.documents.generator import detect_doc_request, generate_document
            doc_info = detect_doc_request(text)

            if doc_info:
                # Document request — send ack, then generate
                await web_client.chat_postMessage(
                    channel=channel_id,
                    text=f"_Generating your {doc_info['format'].upper()}..._",
                )
                print(f"[Slack] Document request detected: {doc_info['format']}")
                try:
                    doc_result = await generate_document(text, doc_info)

                    if "error" in doc_result:
                        await web_client.chat_postMessage(
                            channel=channel_id,
                            text=f"*Error:* Document generation failed — {doc_result['error']}",
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
                    error_msg = f"{type(e).__name__}: {str(e)[:200]}"
                    print(f"[Slack] Document error: {error_msg}")
                    print(f"[Slack] Traceback:\n{traceback.format_exc()}")
                    await web_client.chat_postMessage(
                        channel=channel_id,
                        text=f"*Error generating document:* {error_msg}",
                    )
                return

            # Everything goes through the conversation engine now
            result = await send_to_server(text)

            response_text = format_response(result)
            add_to_history("assistant", response_text)

            # Check if an execution was triggered
            actions = result.get("actions", [])
            has_execution = "execute" in actions

            if has_execution:
                # Send the conversational response, then note the execution
                await web_client.chat_postMessage(
                    channel=channel_id,
                    text=response_text,
                )
                await web_client.chat_postMessage(
                    channel=channel_id,
                    text="_Execution started. I'll report back when it's done._",
                )
            else:
                await web_client.chat_postMessage(
                    channel=channel_id,
                    text=response_text,
                )

            print(f"[Slack] Responding: {response_text[:100]}...")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"[Slack] Handler error: {error_msg}")
            print(f"[Slack] Traceback:\n{traceback.format_exc()}")
            try:
                await web_client.chat_postMessage(
                    channel=channel_id,
                    text=f"*Internal error:* {error_msg}",
                )
            except Exception:
                pass

    socket_client.socket_mode_request_listeners.append(handle_event)

    print("NEXUS Slack listener starting...")
    await socket_client.connect()
    print("NEXUS Slack listener connected.")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(start_slack_listener())
