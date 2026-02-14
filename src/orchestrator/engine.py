"""
NEXUS Orchestration Facade (ARCH-001)

Thin adapter over LangGraph orchestrator. All directive execution flows through
the LangGraph graph (graph.py). The Executor (executor.py) remains as an
explicit fast-path toggle.

Retained from the original ReasoningEngine:
  - understand()      — Haiku-based NLU for CEO message classification
  - fast_decompose()  — quick task decomposition (used by graph nodes too)
  - notify_slack()    — Slack notification helper
  - handle_message()  — message routing (now delegates to LangGraph for directives)

Retired:
  - ReasoningEngine tick loop (_loop / _tick)
  - _dispatch_engineers, _run_qa, _run_code_review, etc.
  - All tick-based polling and cooldown logic

See also: docs/ADR-001-consolidate-orchestration.md
"""

import asyncio
import json
import logging
import os
import uuid

from src.agents.base import Decision, allm_call
from src.agents.implementations import extract_json
from src.agents.org_chart import HAIKU, SONNET
from src.memory.store import memory
from src.observability.logging import directive_id_var

logger = logging.getLogger("nexus.engine")


async def notify_slack(message: str, thread_ts: str | None = None):
    try:
        from src.slack.listener import format_code_output, get_channel_id, get_slack_client, md_to_slack
        client = get_slack_client()
        channel = get_channel_id()
        if client and channel:
            slack_text = md_to_slack(message)
            kwargs = {"channel": channel, "text": slack_text}
            if thread_ts:
                kwargs["thread_ts"] = thread_ts
            if '```' in message:
                blocks = format_code_output(message)
                if blocks:
                    kwargs["blocks"] = blocks  # type: ignore[assignment]
            await client.chat_postMessage(**kwargs)  # type: ignore[arg-type]
    except Exception as e:
        logger.error(f"Slack: {e}")


async def fast_decompose(text: str, directive_id: str) -> int:
    """Break a directive into coding tasks via LLM. Returns count of tasks created."""
    prompt = f"""Break this into 5-12 coding tasks engineers can start immediately:
"{text}"
JSON array: [{{"id":"task-1","title":"...","description":"...","specialty":"frontend/backend/fullstack","priority":10,"depends_on":[]}}]
CODE ONLY tasks. No planning. No docs. JSON array only."""

    raw, _ = await allm_call(prompt, SONNET, max_tokens=3000)
    data = extract_json(raw)
    tasks = data if isinstance(data, list) else (data.get("tasks", []) if isinstance(data, dict) else [])

    created = 0
    for task in tasks:
        tid = task.get("id", f"task-{created+1}")
        try:
            memory.create_board_task(
                task_id=f"{directive_id}-{tid}", directive_id=directive_id,
                title=task.get("title", f"Task {created+1}"),
                description=task.get("description", ""),
                depends_on=[f"{directive_id}-{d}" for d in task.get("depends_on", [])],
                priority=task.get("priority", 5))
            created += 1
        except Exception as e:
            logger.error(f"Task create failed: {e}")

    return created


async def understand(message: str, directive=None) -> dict:
    """Classify a CEO message into an intent using Haiku NLU."""
    state = ""
    if directive:
        state = f"Active: {directive['text']} ({directive['status']})"
        board = memory.get_board_tasks(directive["id"])
        if board:
            c = sum(1 for t in board if t["status"] == "complete")
            state += f" | {c}/{len(board)} tasks done"
        defects = memory.get_open_defects(directive["id"])
        if defects:
            state += f" | {len(defects)} open defects"
        entries = memory.get_context_for_directive(directive["id"])
        if entries:
            state += "\nRecent: " + "; ".join(
                f"{e['author']}:{e['type']}" for e in entries[-5:])

    prompt = f"""Classify CEO message. State: {state or 'Idle.'}
Message: "{message}"
One of: new_directive, feedback, course_correct, question, status, chat, stop, hire, fire
JSON: {{"intent":"...","summary":"...","urgency":"normal","target":"","response":"for q/status/chat"}}"""

    try:
        raw, _ = await allm_call(prompt, HAIKU, max_tokens=500)
        cleaned = raw.strip()
        if "```" in cleaned:
            cleaned = cleaned.split("```json")[-1].split("```")[0].strip() if "```json" in cleaned else cleaned.split("```")[1].strip()
        return json.loads(cleaned)  # type: ignore[no-any-return]
    except Exception:
        return {"intent": "chat", "summary": message[:80], "urgency": "normal",
                "target": "", "response": "Could you rephrase?"}


class OrchestrationFacade:
    """Message-handling facade that routes directives to LangGraph.

    Replaces the former ReasoningEngine tick-based loop. Directives are now
    executed via the LangGraph graph (``compile_nexus_dynamic``), while
    conversational messages (status, chat, hire/fire) are handled inline.
    """

    def __init__(self):
        self.running = False
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._thread_ts: dict[str, str] = {}

    async def _notify(self, message: str, did: str | None = None):
        thread_ts = self._thread_ts.get(did) if did else None
        await notify_slack(message, thread_ts=thread_ts)

    async def start(self):
        """Initialize stores and mark the facade as running."""
        memory.emit_event("engine", "starting", {})

        try:
            from src.ml.store import ml_store
            ml_store.init()
            logger.info("ML learning store initialized")
        except Exception as e:
            logger.warning("ML store init failed (non-fatal): %s", e)

        try:
            from src.ml.knowledge_store import knowledge_store
            knowledge_store.init()
            logger.info("Knowledge store initialized")
        except Exception as e:
            logger.warning("Knowledge store init failed (non-fatal): %s", e)

        self.running = True
        memory.emit_event("engine", "running", {})
        logger.info("Nexus orchestration facade running — LangGraph primary path")

    async def stop(self):
        """Cancel any in-flight directive tasks and shut down."""
        self.running = False
        for task_id, task in self._active_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._active_tasks.clear()

    # ------------------------------------------------------------------
    # Directive execution via LangGraph
    # ------------------------------------------------------------------

    async def _execute_directive_via_graph(self, directive_id: str, text: str, source: str = "api"):
        """Run a directive through the full LangGraph pipeline."""
        try:
            from src.orchestrator.graph import compile_nexus_dynamic
            from src.orchestrator.state import NexusState

            nexus_app = compile_nexus_dynamic()
            project_path = os.environ.get(
                "NEXUS_PROJECT_PATH", os.path.expanduser("~/Projects/nexus")
            )

            initial_state = NexusState(
                directive=text,
                source=source,  # type: ignore[arg-type]
                session_id=directive_id,
                project_path=project_path,
            )

            config = {"configurable": {"thread_id": directive_id}}
            await self._notify(f"On it. Running through the org now.", directive_id)

            result = await nexus_app.ainvoke(initial_state.model_dump(), config=config)

            # Update memory with completion status
            memory.update_directive(directive_id, status="complete")

            demo = result.get("demo_summary", "")
            cost = result.get("cost", {}).get("total_cost_usd", 0)
            await self._notify(
                f"*Directive complete!*\n\n{demo}\n\n*Cost:* ${cost:.2f}",
                directive_id,
            )

        except Exception as e:
            logger.error("LangGraph execution failed for %s: %s", directive_id, e, exc_info=True)
            memory.update_directive(directive_id, status="error")
            await self._notify(f"Execution failed: {e}", directive_id)

        finally:
            self._active_tasks.pop(directive_id, None)

    # ------------------------------------------------------------------
    # Message handling (public API — used by server.py endpoints)
    # ------------------------------------------------------------------

    async def handle_message(self, message, source="slack", thread_ts=None):
        """Classify a message and route it appropriately.

        Conversational intents are handled inline. Directives are dispatched
        to the LangGraph pipeline asynchronously.
        """
        memory.add_message("user", message, source)
        directive = memory.get_active_directive()
        intent = await understand(message, directive)

        if thread_ts:
            if directive:
                self._thread_ts[directive["id"]] = thread_ts
            self._pending_thread_ts = thread_ts

        handler = {
            "new_directive": self._h_new, "feedback": self._h_feedback,
            "course_correct": self._h_pivot, "question": self._h_question,
            "status": self._h_status, "chat": self._h_chat,
            "stop": self._h_stop,
        }.get(intent["intent"], self._h_chat)

        response = await handler(message, intent, directive)
        memory.add_message("assistant", response, source)
        return response

    async def _h_new(self, msg, intent, cur):
        if cur and cur["status"] not in ("complete", "cancelled"):
            memory.update_directive(cur["id"], status="paused")
        did = f"dir-{uuid.uuid4().hex[:8]}"
        memory.create_directive(did, msg)
        memory.post_context("garrett", "directive", msg, did)
        if hasattr(self, '_pending_thread_ts') and self._pending_thread_ts:
            self._thread_ts[did] = self._pending_thread_ts
        directive_id_var.set(did)

        # ML: analyze against historical directives
        try:
            from src.ml.similarity import analyze_new_directive, format_briefing
            analysis = analyze_new_directive(msg)
            if analysis["has_precedent"]:
                briefing = format_briefing(analysis)
                await self._notify(f"*ML Intelligence Briefing:*\n{briefing}", did)
        except Exception as e:
            logger.debug("ML briefing skipped: %s", e)

        # Launch LangGraph execution in background
        task = asyncio.create_task(
            self._execute_directive_via_graph(did, msg)
        )
        self._active_tasks[did] = task

        return f"Directive `{did}` created. LangGraph pipeline started."

    async def _h_feedback(self, msg, intent, d):
        if not d:
            return "No active project."
        memory.post_context("garrett", "feedback", msg, d["id"])
        return "Feedback received. Team is adjusting."

    async def _h_pivot(self, msg, intent, d):
        if not d:
            return "Nothing active."
        memory.post_context("garrett", "interruption", msg, d["id"])
        # Cancel existing execution if running
        old_task = self._active_tasks.pop(d["id"], None)
        if old_task:
            old_task.cancel()
        memory.update_directive(d["id"], status="received")

        # Re-launch with new direction
        task = asyncio.create_task(
            self._execute_directive_via_graph(d["id"], msg)
        )
        self._active_tasks[d["id"]] = task
        return "Pivoting. Restarting with new direction via LangGraph."

    async def _h_question(self, msg, intent, d):
        r = intent.get("response", "")
        return r if r and len(r) > 15 else await self._status(d)

    async def _h_status(self, msg, intent, d):
        return await self._status(d)

    async def _h_chat(self, msg, intent, d):
        return intent.get("response", "What should we build?")

    async def _h_stop(self, msg, intent, d):
        if not d:
            return "Nothing active."
        did = d["id"]
        # Cancel LangGraph execution if running
        old_task = self._active_tasks.pop(did, None)
        if old_task:
            old_task.cancel()
        memory.update_directive(did, status="cancelled")
        return f"Cancelled `{did}`."

    async def _status(self, d):
        if not d:
            return "Standing by."
        board = memory.get_board_tasks(d["id"])
        defects = memory.get_open_defects(d["id"])
        c = sum(1 for t in board if t["status"] == "complete")
        ip = sum(1 for t in board if t["status"] in ("claimed", "in_progress"))
        working = memory.get_working_agents()

        lines = [f"*{d['text'][:80]}* — {d['status']}"]
        if board:
            lines.append(f"Tasks: {c}/{len(board)} done, {ip} active")
        if defects:
            lines.append(f"Open defects: {len(defects)}")
        if working:
            lines.append("Working: " + ", ".join(a["name"] for a in working))

        # Show if LangGraph is actively running
        if d["id"] in self._active_tasks and not self._active_tasks[d["id"]].done():
            lines.append("LangGraph pipeline: *running*")

        return "\n".join(lines)


# Module-level singleton — drop-in replacement for the old `engine` variable
engine = OrchestrationFacade()
