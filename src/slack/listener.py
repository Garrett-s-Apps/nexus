"""
NEXUS Slack Listener (v1)

Listens for messages in #garrett-nexus and routes them directly to the
reasoning engine. No more HTTP round-trip to the server.

Keeps: file download/parsing, markdown-to-slack conversion.
Removes: old server routing, category formatting, in-memory history.
"""

import asyncio
import os
import re
import tempfile
import traceback

import aiohttp
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web.async_client import AsyncWebClient

from src.config import get_key
from src.sessions.cli_pool import cli_pool
from src.tools.web_search import needs_web_search, search as web_search, format_results_for_context


def md_to_slack(text: str) -> str:
    """Convert markdown/HTML to Slack mrkdwn format.

    Handles code blocks, inline code, bold, links, lists, and HTML entities.
    Preserves code blocks verbatim (Slack renders ``` natively).
    """
    # Step 1: Extract code blocks to protect them from other transformations
    code_blocks = []
    def _save_code_block(match):
        code_blocks.append(match.group(0))
        return f"\x00CODE_BLOCK_{len(code_blocks) - 1}\x00"

    # Match fenced code blocks (```lang\n...\n```) — strip language hint
    text = re.sub(r'```\w*\n(.*?)```', lambda m: f"```\n{m.group(1)}```", text, flags=re.DOTALL)
    text = re.sub(r'```.*?```', _save_code_block, text, flags=re.DOTALL)

    # Step 2: Strip HTML tags (Claude Code CLI can output HTML)
    text = re.sub(r'<(?!http|mailto|#|@|!)/?[a-zA-Z][^>]*>', '', text)

    # Step 3: HTML entities
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    text = text.replace('&nbsp;', ' ')

    # Step 4: Markdown → Slack mrkdwn
    text = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    text = re.sub(r'__(.+?)__', r'*\1*', text)
    text = re.sub(r'(?<![`*])`([^`\n]+)`(?![`*])', r'`\1`', text)  # inline code
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<\2|\1>', text)
    text = re.sub(r'^[\-\*]\s+', '•  ', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '•  ', text, flags=re.MULTILINE)  # numbered lists
    text = re.sub(r'^[\-\*]{3,}$', '———', text, flags=re.MULTILINE)
    text = text.replace('***', '*')

    # Step 5: Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Step 6: Restore code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODE_BLOCK_{i}\x00", block)

    return text.strip()


def format_code_output(output: str, agent_name: str = "") -> list[dict]:
    """Format agent output with code into Slack Block Kit blocks.

    Returns a list of Slack blocks. Code sections get their own code blocks.
    Non-code text gets mrkdwn formatting.
    """
    blocks = []

    if agent_name:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"*{agent_name}* completed:"}],
        })

    # Split on code fences
    parts = re.split(r'(```\w*\n.*?```)', output, flags=re.DOTALL)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if part.startswith('```'):
            # Extract code content (strip fences and language hint)
            code = re.sub(r'^```\w*\n?', '', part)
            code = re.sub(r'\n?```$', '', code)
            if len(code) > 2900:
                code = code[:2900] + "\n... (truncated)"
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"```{code}```"},
            })
        else:
            text = md_to_slack(part)
            if len(text) > 2900:
                text = text[:2900] + "\n..."
            if text:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text},
                })

    return blocks


async def download_and_parse_file(url: str, filename: str, bot_token: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"Authorization": f"Bearer {bot_token}"}) as resp:
                if resp.status != 200:
                    return f"(Failed to download: HTTP {resp.status})"

                text_exts = {"py", "js", "ts", "jsx", "tsx", "json", "yaml", "yml",
                             "html", "css", "md", "csv", "txt", "xml", "sh", "bash",
                             "sql", "toml", "ini", "cfg", "env", "log"}
                if ext in text_exts:
                    content = await resp.text()
                    if len(content) > 5000:
                        content = content[:5000] + "\n... (truncated)"
                    return f"```\n{content}\n```"

                file_bytes = await resp.read()
                with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name

                try:
                    content = ""
                    if ext in ("docx", "doc"):
                        from docx import Document
                        doc = Document(tmp_path)
                        content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                    elif ext in ("xlsx", "xls"):
                        import openpyxl
                        wb = openpyxl.load_workbook(tmp_path, read_only=True)
                        rows = []
                        for sheet in wb.sheetnames[:3]:
                            ws = wb[sheet]
                            rows.append(f"--- Sheet: {sheet} ---")
                            for row in ws.iter_rows(max_row=50, values_only=True):
                                rows.append(" | ".join(str(c) if c else "" for c in row))
                        content = "\n".join(rows)
                    elif ext in ("pptx", "ppt"):
                        from pptx import Presentation
                        prs = Presentation(tmp_path)
                        slides = []
                        for i, slide in enumerate(prs.slides, 1):
                            texts = [s.text for s in slide.shapes if hasattr(s, "text") and s.text.strip()]
                            if texts:
                                slides.append(f"--- Slide {i} ---\n" + "\n".join(texts))
                        content = "\n\n".join(slides)
                    elif ext == "pdf":
                        try:
                            import fitz
                            pdf_doc = fitz.open(tmp_path)
                            content = "\n".join(page.get_text() for page in pdf_doc[:10])
                        except ImportError:
                            content = "(Install PyMuPDF for PDF reading)"
                    else:
                        content = f"(Unsupported file type: .{ext})"

                    if len(content) > 8000:
                        content = content[:8000] + "\n... (truncated)"
                    return f"```\n{content}\n```" if content else "(Empty or unreadable)"
                finally:
                    os.unlink(tmp_path)

    except Exception as e:
        return f"(Failed to read {filename}: {e})"


async def upload_file_to_slack(web_client: AsyncWebClient, channel: str,
                                filepath: str, title: str = "", comment: str = ""):
    try:
        await web_client.files_upload_v2(
            channel=channel, file=filepath,
            title=title or os.path.basename(filepath), initial_comment=comment)
    except Exception as e:
        print(f"[Slack] File upload failed: {e}")


_web_client: AsyncWebClient | None = None
_channel_id: str | None = None


def get_slack_client() -> AsyncWebClient | None:
    return _web_client


def get_channel_id() -> str | None:
    return _channel_id


async def start_slack_listener():
    global _web_client, _channel_id

    bot_token = get_key("SLACK_BOT_TOKEN")
    app_token = get_key("SLACK_APP_TOKEN")

    if not bot_token or not app_token:
        print("[Slack] Missing tokens — Slack disabled")
        return

    web_client = AsyncWebClient(token=bot_token)
    socket_client = SocketModeClient(app_token=app_token, web_client=web_client)
    _web_client = web_client

    try:
        result = await web_client.conversations_list(types="public_channel,private_channel", limit=200)
        for ch in result["channels"]:
            if ch["name"] == "garrett-nexus":
                _channel_id = ch["id"]
                break
        if not _channel_id:
            print("[Slack] Channel #garrett-nexus not found")
    except Exception as e:
        print(f"[Slack] Channel lookup failed: {e}")

    auth = await web_client.auth_test()
    bot_user_id = auth["user_id"]

    async def handle_event(client: SocketModeClient, req: SocketModeRequest):
        await client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        if req.type != "events_api":
            return
        event = req.payload.get("event", {})
        if event.get("type") != "message" or event.get("subtype") or event.get("user") == bot_user_id:
            return

        channel_id = event.get("channel", "")
        text = event.get("text", "").strip()

        files = event.get("files", [])
        file_context = ""
        if files:
            for f in files:
                fname = f.get("name", "unknown")
                url = f.get("url_private", "")
                if url:
                    file_context += f"\n[File: {fname}]\n"
                    file_context += await download_and_parse_file(url, fname, bot_token)
            text = f"{text}\n{file_context}" if text else f"[Sent files]{file_context}"

        if not text:
            return

        print(f"[Slack] Received: {text[:100]}")

        try:
            from src.orchestrator.engine import engine

            thread_ts = event.get("thread_ts") or event.get("ts")
            is_threaded_reply = event.get("thread_ts") is not None

            # Enrich with web search when the question warrants it
            if needs_web_search(text):
                await web_client.reactions_add(channel=channel_id, name="mag", timestamp=event.get("ts"))
                try:
                    search_results = await web_search(text, num_results=5)
                    web_context = format_results_for_context(search_results)
                    text = f"{text}\n\n---\n{web_context}"
                except Exception as e:
                    print(f"[Slack] Web search failed (non-fatal): {e}")

            # Route threaded replies through persistent CLI sessions when available
            if is_threaded_reply and cli_pool.active_count() > 0:
                session = cli_pool._sessions.get(thread_ts)
                if session and session.alive:
                    response = await session.send(text)
                else:
                    response = await engine.handle_message(text, source="slack", thread_ts=thread_ts)
            else:
                response = await engine.handle_message(text, source="slack", thread_ts=thread_ts)

            slack_text = md_to_slack(response)

            # Use Block Kit for responses containing code
            has_code = '```' in response or '`' in response
            if has_code:
                blocks = format_code_output(response)
                if blocks:
                    await web_client.chat_postMessage(
                        channel=channel_id, text=slack_text[:3900],
                        blocks=blocks, thread_ts=thread_ts)
                else:
                    await web_client.chat_postMessage(
                        channel=channel_id, text=slack_text[:3900],
                        thread_ts=thread_ts)
            elif len(slack_text) > 3900:
                chunks = [slack_text[i:i+3900] for i in range(0, len(slack_text), 3900)]
                for chunk in chunks:
                    await web_client.chat_postMessage(
                        channel=channel_id, text=chunk,
                        thread_ts=thread_ts)
            else:
                await web_client.chat_postMessage(
                    channel=channel_id, text=slack_text,
                    thread_ts=thread_ts)

            print(f"[Slack] Responded in thread {thread_ts}: {slack_text[:100]}...")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"[Slack] Error: {error_msg}")
            traceback.print_exc()
            try:
                await web_client.chat_postMessage(channel=channel_id, text=f"Internal error: {error_msg}")
            except Exception:
                pass

    socket_client.socket_mode_request_listeners.append(handle_event)
    print("[Slack] Connecting...")
    await socket_client.connect()
    print("[Slack] Connected and listening.")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(start_slack_listener())
