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
from src.documents.generator import (
    _gather_internal_context,
    _gather_web_context,
    _needs_web_enrichment,
    generate_document,
)
from src.memory.store import memory
from src.sessions.cli_pool import cli_pool


async def classify_doc_request(text: str) -> dict | None:
    """Use Haiku to determine the best response format for a message.

    Returns:
        {"format": "pdf"|"docx"|"pptx"|"image"} — generate a file
        {"format": "text"} — respond with formatted text (enriched with internal data)
        None — not a data/document request, route normally
    """
    try:
        from src.agents.base import allm_call
        from src.agents.org_chart import HAIKU
        prompt = f"""Determine the best response format for this message.
Message: "{text}"

Respond with JSON: {{"doc": true, "format": "pdf"|"docx"|"pptx"|"image"|"text", "title": "short title"}}
Or if the message is an ACTION COMMAND or general chat: {{"doc": false}}

CRITICAL: If the message is an ACTION (hire, fire, deploy, build, fix, ship, run, test, etc.),
respond with {{"doc": false}}. Actions are NOT document requests.

Rules for choosing format:
- {{"doc": false}} for actions: hire someone, fire someone, deploy, build, fix bugs, run tests, etc.
- If the user explicitly says a format (pdf, word, slides, image, etc.), use THAT format
- "text" for quick lookups like "show me X", "what's our X", "list the X", "who reports to X" — answer inline
- "image" for visual diagrams, flowcharts, architecture diagrams — when the user wants a VISUAL representation
- "pdf" for formal reports, summaries, one-pagers, or anything they'd want to download/share
- "docx" for longer documents, specs, proposals, letters
- "pptx" for presentations, decks, pitches
- When in doubt between "text" and a file: prefer "text" for quick info, prefer a file for formal/shareable deliverables
- "show me the org chart" = "text" (quick view). "send me a PDF of the org chart" = "pdf" (formal deliverable)
- "hire a SF team" = {{"doc": false}} (action, not a document!)"""

        raw, _ = await allm_call(prompt, HAIKU, max_tokens=200)
        cleaned = raw.strip()
        if "```" in cleaned:
            cleaned = cleaned.split("```json")[-1].split("```")[0].strip() if "```json" in cleaned else cleaned.split("```")[1].strip()
        import json
        result = json.loads(cleaned)
        if result.get("doc"):
            return {"format": result.get("format", "text"), "title": result.get("title", "")}
    except Exception as e:
        print(f"[Slack] Doc classification failed (non-fatal): {e}")
    return None


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
                "text": {"type": "mrkdwn", "text": f"```{code}```"},  # type: ignore[dict-item]
            })
        else:
            text = md_to_slack(part)
            if len(text) > 2900:
                text = text[:2900] + "\n..."
            if text:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text},  # type: ignore[dict-item]
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
                    elif ext in ("png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico"):
                        # Keep the temp file for the CLI session to read visually
                        import shutil
                        img_dir = os.path.join(tempfile.gettempdir(), "nexus_images")
                        os.makedirs(img_dir, exist_ok=True)
                        img_path = os.path.join(img_dir, filename)
                        shutil.copy2(tmp_path, img_path)
                        content = f"(Image saved to {img_path} — analyze this image)"
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
                                filepath: str, title: str = "", comment: str = "",
                                thread_ts: str | None = None):
    try:
        kwargs = dict(
            channel=channel, file=filepath,
            title=title or os.path.basename(filepath), initial_comment=comment,
        )
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        await web_client.files_upload_v2(**kwargs)  # type: ignore[arg-type]
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
        subtype = event.get("subtype", "")
        # Allow file_share (images/attachments) through; block bot messages, edits, etc.
        ignored_subtypes = {"bot_message", "message_changed", "message_deleted", "channel_join", "channel_leave"}
        if event.get("type") != "message" or subtype in ignored_subtypes or event.get("user") == bot_user_id:
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

        thinking_msg = None
        thread_ts = event.get("thread_ts") or event.get("ts")
        memory.emit_event("slack", "message_received", {
            "text": text[:200], "thread_ts": thread_ts,
            "user": event.get("user", ""), "has_files": bool(files),
        })

        try:
            from src.orchestrator.engine import engine

            async def safe_react(name):
                try:
                    await web_client.reactions_add(channel=channel_id, name=name, timestamp=event.get("ts"))
                except Exception:
                    pass  # reactions:write scope may not be granted

            # Send a "working on it" indicator so the user knows we received it
            try:
                result = await web_client.chat_postMessage(
                    channel=channel_id,
                    text=":hourglass_flowing_sand: Processing...",
                    thread_ts=thread_ts,
                )
                thinking_msg = result.get("ts")
            except Exception:
                pass

            # LLM-based: detect if the message is asking for a document or data
            doc_info = await classify_doc_request(text)
            if doc_info:
                memory.emit_event("slack", "doc_classified", {
                    "format": doc_info["format"], "title": doc_info.get("title", ""),
                    "thread_ts": thread_ts,
                })
                if doc_info["format"] == "text":
                    # Enrich with internal + web data, let engine respond with formatted text
                    internal_context = _gather_internal_context(text)
                    web_context = ""
                    search_query = _needs_web_enrichment(text, bool(internal_context))
                    if search_query:
                        web_context = await _gather_web_context(search_query)
                    context_parts = []
                    if internal_context:
                        context_parts.append(internal_context)
                    if web_context:
                        context_parts.append(web_context)
                    if context_parts:
                        text = (
                            f"{text}\n\n"
                            f"Use the following real data to answer. "
                            f"Prefer internal data over web results. "
                            f"Format your response for Slack readability.\n\n"
                            + "\n".join(context_parts)
                        )
                    # Fall through to engine/CLI below
                else:
                    try:
                        if thinking_msg:
                            await web_client.chat_update(
                                channel=channel_id, ts=thinking_msg,
                                text=f":page_facing_up: Generating {doc_info['format'].upper()}...")
                        memory.emit_event("slack", "doc_generating", {
                            "format": doc_info["format"], "thread_ts": thread_ts,
                        })
                        result = await generate_document(text, doc_info)
                        if "error" in result:
                            memory.emit_event("slack", "doc_failed", {
                                "error": result["error"][:200], "thread_ts": thread_ts,
                            })
                            await web_client.chat_postMessage(
                                channel=channel_id,
                                text=f":warning: Document generation failed: {result['error']}",
                                thread_ts=thread_ts)
                        else:
                            memory.emit_event("slack", "doc_complete", {
                                "format": result["format"],
                                "title": result.get("title", "Document"),
                                "thread_ts": thread_ts,
                            })
                            await upload_file_to_slack(
                                web_client, channel_id,
                                result["filepath"],
                                title=result.get("title", "Document"),
                                comment=f"Generated {result['format'].upper()}: *{result.get('title', 'Document')}*",
                                thread_ts=thread_ts)
                        if thinking_msg:
                            try:
                                await web_client.chat_delete(channel=channel_id, ts=thinking_msg)
                            except Exception:
                                pass
                        return
                    except Exception as e:
                        print(f"[Slack] Document generation failed, falling through to engine: {e}")

            # All messages go to Claude Code (Opus) first. It decides
            # whether to answer directly or dispatch to the engine/agents.
            response = None
            cli_failed = False
            project_path = os.environ.get("NEXUS_PROJECT_PATH", os.path.expanduser("~/Projects/nexus"))

            try:
                await safe_react("robot_face")
                session = await cli_pool.get_or_create(thread_ts, project_path)
                if session.alive:
                    memory.emit_event("slack", "cli_routed", {
                        "thread_ts": thread_ts, "pid": session.process.pid if session.process else None,
                    })
                    response = await session.send(text)
                else:
                    cli_failed = True
            except Exception as e:
                cli_failed = True
                print(f"[Slack] CLI session failed: {e}")

            # Engine is a fallback ONLY when the CLI process itself failed.
            # Normal conversational responses (even short ones) stay as-is.
            cli_error = response and (response == "(No response from CLI)" or response.startswith("CLI error"))
            if cli_failed or cli_error:
                memory.emit_event("slack", "engine_fallback", {
                    "reason": response[:200] if response else "cli unavailable",
                    "thread_ts": thread_ts,
                })
                response = await engine.handle_message(text, source="slack", thread_ts=thread_ts)

            memory.emit_event("slack", "response_sent", {
                "text": (response or "")[:200], "thread_ts": thread_ts,
            })
            if not response:
                response = ""
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

            # Remove the "Processing..." indicator
            if thinking_msg:
                try:
                    await web_client.chat_delete(channel=channel_id, ts=thinking_msg)
                except Exception:
                    pass

            print(f"[Slack] Responded in thread {thread_ts}: {slack_text[:100]}...")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"[Slack] Error: {error_msg}")
            traceback.print_exc()
            # Remove thinking indicator on error
            if thinking_msg:
                try:
                    await web_client.chat_delete(channel=channel_id, ts=thinking_msg)
                except Exception:
                    pass
            try:
                await web_client.chat_postMessage(
                    channel=channel_id,
                    text=f":warning: Error processing your request:\n`{error_msg}`",
                    thread_ts=thread_ts,
                )
            except Exception:
                pass

    socket_client.socket_mode_request_listeners.append(handle_event)
    print("[Slack] Connecting...")
    await socket_client.connect()
    cli_pool.start_cleanup_loop()
    print("[Slack] Connected and listening. CLI session pool active.")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(start_slack_listener())
