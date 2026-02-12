"""
NEXUS Reasoning Engine v3.0 — Fully Autonomous

Pipeline:
  directive → decompose → engineers build (parallel) → QA tests (auto) → defects filed →
  engineers fix → QA re-tests → code review → done

Everything automatic. CEO only gives directives and fires people.
PMs enrich tasks. QA files defects. Engineers fix them. Loop until clean.
"""

import asyncio
import json
import logging
import time
import uuid

from src.agents.base import Agent, Decision, allm_call
from src.agents.implementations import create_agent, create_all_agents, extract_json
from src.agents.org_chart import HAIKU, ORG_CHART, SONNET
from src.memory.store import memory

logger = logging.getLogger("nexus.engine")

MAX_QA_CYCLES = 3  # prevent infinite defect loops


async def notify_slack(message: str, thread_ts: str = None):
    try:
        from src.slack.listener import format_code_output, get_channel_id, get_slack_client, md_to_slack
        client = get_slack_client()
        channel = get_channel_id()
        if client and channel:
            slack_text = md_to_slack(message)
            kwargs = {"channel": channel, "text": slack_text}
            if thread_ts:
                kwargs["thread_ts"] = thread_ts
            # Use Block Kit for messages with code
            if '```' in message:
                blocks = format_code_output(message)
                if blocks:
                    kwargs["blocks"] = blocks
            await client.chat_postMessage(**kwargs)
    except Exception as e:
        logger.error(f"Slack: {e}")


async def fast_decompose(text: str, directive_id: str) -> int:
    prompt = f"""Break this into 5-12 coding tasks engineers can start immediately:
"{text}"
JSON array: [{{"id":"task-1","title":"...","description":"...","specialty":"frontend/backend/fullstack","priority":10,"depends_on":[]}}]
CODE ONLY tasks. No planning. No docs. JSON array only."""

    raw, _ = await allm_call(prompt, SONNET, max_tokens=3000)
    data = extract_json(raw)
    tasks = data if isinstance(data, list) else (data.get("tasks", []) if isinstance(data, dict) else [])

    if not tasks:
        import re
        match = re.search(r'\[[\s\S]*\]', raw)
        if match:
            try: tasks = json.loads(match.group())
            except (json.JSONDecodeError, ValueError): tasks = []

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


# ---------------------------------------------------------------------------
# NLU
# ---------------------------------------------------------------------------

async def understand(message: str, directive=None) -> dict:
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
        return json.loads(cleaned)
    except Exception:
        return {"intent": "chat", "summary": message[:80], "urgency": "normal",
                "target": "", "response": "Could you rephrase?"}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ReasoningEngine:

    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.running = False
        self.tick_interval = 6
        self.max_concurrent = 5
        self._tick_count = 0
        self._task = None
        self._last_event_id = 0
        self._cooldowns: dict[str, float] = {}
        self._cooldown_s = 35
        self._qa_cycles: dict[str, int] = {}  # directive_id -> qa cycle count
        self._thread_ts: dict[str, str] = {}  # directive_id -> slack thread_ts

    async def _notify(self, message: str, did: str = None):
        """Send a Slack notification in the directive's thread."""
        thread_ts = self._thread_ts.get(did) if did else None
        await notify_slack(message, thread_ts=thread_ts)

    async def start(self):
        memory.emit_event("engine", "starting", {})
        self.agents = create_all_agents()
        self._last_event_id = memory.get_latest_event_id()
        self.running = True
        self._task = asyncio.create_task(self._loop())
        memory.emit_event("engine", "running", {"agents": len(self.agents)})
        logger.info(f"Nexus v3 running — {len(self.agents)} agents")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

    async def _loop(self):
        while self.running:
            try: await self._tick()
            except Exception as e: logger.error(f"Tick: {e}", exc_info=True)
            await asyncio.sleep(self.tick_interval)

    async def _tick(self):
        self._tick_count += 1

        directive = memory.get_active_directive()
        if not directive or directive["status"] in ("complete", "cancelled"):
            return

        new = memory.get_events_since(self._last_event_id, limit=50)
        if new:
            self._last_event_id = new[-1]["id"]
        elif self._tick_count % 5 != 0:
            return

        did = directive["id"]
        status = directive["status"]

        if status == "received":
            await self._kickoff(directive)

        elif status == "building":
            # Phase 1: PMs enrich tasks that need context
            await self._run_pms(did)
            # Phase 2: Engineers build
            await self._dispatch_engineers(did)
            # Phase 3: Check if all code is written
            await self._check_build_done(did)

        elif status == "testing":
            # QA reviews, files defects
            await self._run_qa(did)
            await self._check_qa_done(did)

        elif status == "fixing":
            # Engineers fix defects
            await self._dispatch_defect_fixes(did)
            await self._check_fixes_done(did)

        elif status == "reviewing":
            # Code review
            await self._run_code_review(did)
            await self._check_review_done(did)

    # ------------------------------------------------------------------
    # Kickoff
    # ------------------------------------------------------------------

    async def _kickoff(self, directive):
        did = directive["id"]
        await self._notify("On it. Breaking down and starting immediately.", did)

        count = await fast_decompose(directive["text"], did)
        if not count:
            await self._notify("Couldn't decompose. Can you be more specific?", did)
            return

        memory.update_directive(did, status="building")
        self._qa_cycles[did] = 0
        await self._notify(f"{count} tasks created. Engineers starting now.", did)
        await self._dispatch_engineers(did)

    # ------------------------------------------------------------------
    # PMs
    # ------------------------------------------------------------------

    async def _run_pms(self, did):
        now = time.time()
        for pm_id in ["pm_1", "pm_2"]:
            ck = f"pm:{pm_id}:{did}"
            if now - self._cooldowns.get(ck, 0) < 60:
                continue
            agent = self.agents.get(pm_id)
            if not agent or agent.is_running:
                continue
            decision = Decision(act=True, action="Enrich tasks and triage defects", context={})
            asyncio.create_task(self._safe_run(pm_id, decision, did))
            self._cooldowns[ck] = now
            break  # one PM per tick

    # ------------------------------------------------------------------
    # Engineers
    # ------------------------------------------------------------------

    async def _dispatch_engineers(self, did):
        available = memory.get_available_tasks(did)
        if not available:
            return

        available.sort(key=lambda t: t.get("priority", 0), reverse=True)
        now = time.time()
        engineers = ["fe_engineer_1", "fe_engineer_2", "be_engineer_1", "be_engineer_2"]
        dispatched = 0

        for task in available:
            if not memory.are_dependencies_met(task["id"]):
                continue

            best = self._match(task, engineers, now)
            if not best:
                continue

            decision = Decision(act=True, task_id=task["id"],
                               action=f"Build: {task['title']}", context={})
            asyncio.create_task(self._safe_run(best, decision, did))
            self._cooldowns[f"eng:{best}"] = now
            dispatched += 1

            if dispatched >= self.max_concurrent:
                break

    def _match(self, task, engineer_ids, now):
        text = (task.get("title","") + " " + task.get("description","")).lower()
        is_fe = any(w in text for w in ["frontend","ui","component","page","css","react","html"])
        is_be = any(w in text for w in ["backend","api","database","server","auth","endpoint","python"])

        for eid in engineer_ids:
            a = self.agents.get(eid)
            if not a or a.is_running: continue
            if now - self._cooldowns.get(f"eng:{eid}", 0) < self._cooldown_s: continue
            if is_fe and a.specialty == "frontend": return eid
            if is_be and a.specialty == "backend": return eid

        for eid in engineer_ids:
            a = self.agents.get(eid)
            if not a or a.is_running: continue
            if now - self._cooldowns.get(f"eng:{eid}", 0) < self._cooldown_s: continue
            return eid
        return None

    async def _check_build_done(self, did):
        board = memory.get_board_tasks(did)
        if not board: return
        total = len(board)
        complete = sum(1 for t in board if t["status"] == "complete")
        in_prog = sum(1 for t in board if t["status"] in ("claimed", "in_progress"))

        if complete == total:
            memory.update_directive(did, status="testing")
            await self._notify(f"All {total} tasks built. QA is testing now.", did)
        elif complete + in_prog > 0 and self._tick_count % 10 == 0:
            await self._notify(f"Building: {complete}/{total} done, {in_prog} in progress.", did)

    # ------------------------------------------------------------------
    # QA
    # ------------------------------------------------------------------

    async def _run_qa(self, did):
        now = time.time()
        qa_agents = ["qa_lead", "fe_tester", "be_tester"]
        for qa_id in qa_agents:
            ck = f"qa:{qa_id}:{did}"
            if now - self._cooldowns.get(ck, 0) < 45:
                continue
            agent = self.agents.get(qa_id)
            if not agent or agent.is_running:
                continue
            decision = Decision(act=True, action="Test code and file defects", context={})
            asyncio.create_task(self._safe_run(qa_id, decision, did))
            self._cooldowns[ck] = now

    async def _check_qa_done(self, did):
        # Wait for QA agents to finish
        qa_ids = ["qa_lead", "fe_tester", "be_tester"]
        if any(self.agents.get(q) and self.agents[q].is_running for q in qa_ids):
            return

        defects = memory.get_open_defects(did)
        cycle = self._qa_cycles.get(did, 0)

        if defects and cycle < MAX_QA_CYCLES:
            memory.update_directive(did, status="fixing")
            self._qa_cycles[did] = cycle + 1
            await self._notify(f"QA found {len(defects)} defect(s). Engineers are fixing them. (cycle {cycle+1}/{MAX_QA_CYCLES})", did)
        elif defects and cycle >= MAX_QA_CYCLES:
            memory.update_directive(did, status="reviewing")
            await self._notify(f"QA cycle limit reached. {len(defects)} defect(s) remain. Moving to code review.", did)
        else:
            memory.update_directive(did, status="reviewing")
            await self._notify("QA passed. Moving to code review.", did)

    # ------------------------------------------------------------------
    # Defect fixes
    # ------------------------------------------------------------------

    async def _dispatch_defect_fixes(self, did):
        defects = memory.get_open_defects(did)
        if not defects:
            return

        now = time.time()
        engineers = ["fe_engineer_1", "fe_engineer_2", "be_engineer_1", "be_engineer_2"]

        for defect in defects:
            if defect.get("assigned_to") and defect["assigned_to"] in engineers:
                eid = defect["assigned_to"]
            else:
                # Auto-assign
                desc = (defect.get("file_path","") + " " + defect.get("description","")).lower()
                if any(w in desc for w in ["frontend","ui","css","react","html","component"]):
                    eid = "fe_engineer_1"
                else:
                    eid = "be_engineer_1"
                memory.assign_defect(defect["id"], eid)

            agent = self.agents.get(eid)
            if not agent or agent.is_running:
                continue
            ck = f"fix:{eid}"
            if now - self._cooldowns.get(ck, 0) < self._cooldown_s:
                continue

            decision = Decision(act=True, action=f"Fix defect: {defect['title']}", context={})
            asyncio.create_task(self._safe_run(eid, decision, did))
            self._cooldowns[ck] = now

    async def _check_fixes_done(self, did):
        defects = memory.get_open_defects(did)
        engineers = ["fe_engineer_1", "fe_engineer_2", "be_engineer_1", "be_engineer_2"]
        any_fixing = any(self.agents.get(e) and self.agents[e].is_running for e in engineers)

        if not defects and not any_fixing:
            # All defects fixed — back to QA
            memory.update_directive(did, status="testing")
            await self._notify("Defects fixed. Re-testing.", did)

    # ------------------------------------------------------------------
    # Code review
    # ------------------------------------------------------------------

    async def _run_code_review(self, did):
        now = time.time()
        reviewers = ["code_review_lead", "fe_reviewer", "be_reviewer"]
        for rid in reviewers:
            ck = f"cr:{rid}:{did}"
            if now - self._cooldowns.get(ck, 0) < 60:
                continue
            agent = self.agents.get(rid)
            if not agent or agent.is_running:
                continue
            decision = Decision(act=True, action="Review code quality", context={})
            asyncio.create_task(self._safe_run(rid, decision, did))
            self._cooldowns[ck] = now

    async def _check_review_done(self, did):
        reviewers = ["code_review_lead", "fe_reviewer", "be_reviewer"]
        if any(self.agents.get(r) and self.agents[r].is_running for r in reviewers):
            return

        defects = memory.get_open_defects(did)
        if defects:
            memory.update_directive(did, status="fixing")
            await self._notify(f"Code review found {len(defects)} issue(s). Fixing.", did)
        else:
            memory.update_directive(did, status="complete")
            await self._notify("*Project complete!* Code built, tested, and reviewed. Check your project directory.", did)

    # ------------------------------------------------------------------
    # Safe runner
    # ------------------------------------------------------------------

    async def _safe_run(self, agent_id, decision, directive_id):
        agent = self.agents.get(agent_id)
        if not agent:
            return
        try:
            await agent.execute(decision, directive_id)
        except Exception as e:
            logger.error(f"[{agent.name}] Error: {e}", exc_info=True)
            memory.emit_event(agent_id, "agent_error", {
                "error": str(e)[:500],
                "agent": agent.name,
                "action": getattr(decision, 'action', ''),
            })
            # Track failures for potential escalation
            if hasattr(decision, 'task_id') and decision.task_id:
                memory.fail_board_task(decision.task_id, error=str(e)[:500])

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def handle_message(self, message, source="slack", thread_ts=None):
        memory.add_message("user", message, source)
        directive = memory.get_active_directive()
        intent = await understand(message, directive)

        # Store thread_ts so all notifications go to this thread
        if thread_ts:
            if directive:
                self._thread_ts[directive["id"]] = thread_ts
            self._pending_thread_ts = thread_ts  # for new directives

        handler = {
            "new_directive": self._h_new, "feedback": self._h_feedback,
            "course_correct": self._h_pivot, "question": self._h_question,
            "status": self._h_status, "chat": self._h_chat,
            "stop": self._h_stop, "hire": self._h_hire, "fire": self._h_fire,
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
        # Link this directive to the Slack thread it was started in
        if hasattr(self, '_pending_thread_ts') and self._pending_thread_ts:
            self._thread_ts[did] = self._pending_thread_ts
        self._cooldowns.clear()
        return f"Directive `{did}` created. Starting immediately."

    async def _h_feedback(self, msg, intent, d):
        if not d: return "No active project."
        memory.post_context("garrett", "feedback", msg, d["id"])
        self._cooldowns.clear()
        return "Feedback received. Team is adjusting."

    async def _h_pivot(self, msg, intent, d):
        if not d: return "Nothing active."
        memory.post_context("garrett", "interruption", msg, d["id"])
        memory.update_directive(d["id"], status="received")
        self._cooldowns.clear()
        return "Pivoting. Restarting with new direction."

    async def _h_question(self, msg, intent, d):
        r = intent.get("response", "")
        return r if r and len(r) > 15 else await self._status(d)

    async def _h_status(self, msg, intent, d):
        return await self._status(d)

    async def _h_chat(self, msg, intent, d):
        return intent.get("response", "What should we build?")

    async def _h_stop(self, msg, intent, d):
        if not d: return "Nothing active."
        memory.update_directive(d["id"], status="cancelled")
        return f"Cancelled `{d['id']}`."

    async def _h_hire(self, msg, intent, d):
        try:
            raw, _ = await allm_call(f"""Hiring: "{msg}"
Orgs: product(vp_product),engineering(vp_engineering),security(ciso),docs(head_of_docs),analytics(director_analytics)
JSON: {{"id":"snake","name":"Male name","title":"Title","role":"desc","reports_to":"mgr","model":"claude-sonnet-4-20250514","specialty":""}}""", HAIKU)
            details = extract_json(raw)
            if not details: return "Couldn't parse hiring details."
            mgr = self.agents.get(details.get("reports_to", "vp_engineering"))
            if not mgr: return "Manager not found."
            result = await mgr.hire(
                agent_id=details["id"], name=details["name"], title=details["title"],
                role=details["role"], model=details.get("model", SONNET),
                specialty=details.get("specialty", ""))
            self.agents[details["id"]] = create_agent(details["id"])
            return result
        except Exception as e:
            return f"Hiring failed: {e}"

    async def _h_fire(self, msg, intent, d):
        target = intent.get("target", "").lower()
        for aid, cfg in list(ORG_CHART.items()):
            if cfg["name"].lower() == target or aid == target:
                name = cfg["name"]
                self.agents.pop(aid, None)
                ORG_CHART.pop(aid, None)
                memory.emit_event("ceo", "fired", {"agent": name})
                return f"{name} has been let go."
        return f"Couldn't find '{target}'."

    async def _status(self, d):
        if not d: return "Standing by."
        board = memory.get_board_tasks(d["id"])
        defects = memory.get_open_defects(d["id"])
        c = sum(1 for t in board if t["status"] == "complete")
        ip = sum(1 for t in board if t["status"] in ("claimed","in_progress"))
        working = memory.get_working_agents()

        lines = [f"*{d['text'][:80]}* — {d['status']}"]
        if board: lines.append(f"Tasks: {c}/{len(board)} done, {ip} active")
        if defects: lines.append(f"Open defects: {len(defects)}")
        if working: lines.append("Working: " + ", ".join(a["name"] for a in working))
        return "\n".join(lines)


engine = ReasoningEngine()
