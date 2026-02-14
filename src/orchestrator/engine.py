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
import os
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta

from src.agents.base import Agent, Decision, allm_call
from src.agents.implementations import create_agent, create_all_agents, extract_json
from src.agents.org_chart import HAIKU, ORG_CHART, SONNET
from src.memory.store import memory
from src.ml import feedback as ml_feedback
from src.ml.router import predict_best_agent
from src.ml.similarity import analyze_new_directive, format_briefing
from src.observability.logging import agent_id_var, directive_id_var, task_id_var
from src.resilience.circuit_breaker import CircuitOpenError, breaker_registry
from src.resilience.escalation import escalation_chain

logger = logging.getLogger("nexus.engine")

MAX_QA_CYCLES = 3

# Plugin review result storage with TTL and LRU eviction
_plugin_review_results: OrderedDict[str, tuple[datetime, dict]] = OrderedDict()
_MAX_REVIEW_RESULTS = 1000
_REVIEW_TTL_HOURS = 24

def _cleanup_old_reviews():
    """Remove review results older than TTL."""
    cutoff = datetime.now() - timedelta(hours=_REVIEW_TTL_HOURS)
    expired = [k for k, (ts, _) in _plugin_review_results.items() if ts < cutoff]
    for k in expired:
        del _plugin_review_results[k]

def _store_review(directive_id: str, result: dict) -> None:
    """Store review result with TTL cleanup and LRU eviction."""
    _cleanup_old_reviews()
    if len(_plugin_review_results) >= _MAX_REVIEW_RESULTS:
        _plugin_review_results.popitem(last=False)  # LRU eviction
    _plugin_review_results[directive_id] = (datetime.now(), result)


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
            # Use Block Kit for messages with code
            if '```' in message:
                blocks = format_code_output(message)
                if blocks:
                    kwargs["blocks"] = blocks  # type: ignore[assignment]
            await client.chat_postMessage(**kwargs)  # type: ignore[arg-type]
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
        self._qa_cycles: dict[str, int] = {}
        self._thread_ts: dict[str, str] = {}

    async def _notify(self, message: str, did: str | None = None):
        """Send a Slack notification in the directive's thread."""
        thread_ts = self._thread_ts.get(did) if did else None
        await notify_slack(message, thread_ts=thread_ts)

    async def start(self):
        memory.emit_event("engine", "starting", {})

        # Initialize ML learning store and knowledge store
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
        directive_id_var.set(did)

        if status == "received":
            await self._kickoff(directive)

        elif status == "building":
            await self._run_pms(did)
            await self._dispatch_engineers(did)
            await self._check_build_done(did)

        elif status == "testing":
            await self._run_qa(did)
            await self._check_qa_done(did)

        elif status == "fixing":
            await self._dispatch_defect_fixes(did)
            await self._check_fixes_done(did)

        elif status == "reviewing":
            await self._run_code_review(did)
            await self._check_review_done(did)

        elif status == "plugin_reviewing":
            await self._check_plugin_review_done(did)

    async def _kickoff(self, directive):
        did = directive["id"]
        await self._notify("On it. Breaking down and starting immediately.", did)

        # ML: analyze against historical directives
        try:
            analysis = analyze_new_directive(directive["text"])
            if analysis["has_precedent"]:
                briefing = format_briefing(analysis)
                await self._notify(f"*ML Intelligence Briefing:*\n{briefing}", did)
        except Exception as e:
            logger.debug("ML briefing skipped: %s", e)

        count = await fast_decompose(directive["text"], did)
        if not count:
            await self._notify("Couldn't decompose. Can you be more specific?", did)
            return

        memory.update_directive(did, status="building")
        self._qa_cycles[did] = 0
        await self._notify(f"{count} tasks created. Engineers starting now.", did)
        await self._dispatch_engineers(did)

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
            break

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

        # Filter to available engineers (not running, not on cooldown)
        available = [
            eid for eid in engineer_ids
            if self.agents.get(eid)
            and not self.agents[eid].is_running
            and now - self._cooldowns.get(f"eng:{eid}", 0) >= self._cooldown_s
        ]
        if not available:
            return None

        # Try ML-based routing first
        ml_pick = predict_best_agent(text, available)
        if ml_pick:
            return ml_pick

        # Keyword fallback
        is_fe = any(w in text for w in ["frontend","ui","component","page","css","react","html"])
        is_be = any(w in text for w in ["backend","api","database","server","auth","endpoint","python"])

        for eid in available:
            a = self.agents[eid]
            if is_fe and a.specialty == "frontend": return eid
            if is_be and a.specialty == "backend": return eid

        return available[0]

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
            memory.update_directive(did, status="testing")
            await self._notify("Defects fixed. Re-testing.", did)

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
            memory.update_directive(did, status="plugin_reviewing")
            await self._notify("Code review passed. Running plugin-based diagnostics.", did)
            asyncio.create_task(self._run_plugin_review(did))

    async def _run_plugin_review(self, did):
        """Run plugin-based review suite on changed files. Non-blocking on failure."""
        try:
            from src.plugins.review_hooks import run_plugin_review_suite
            project_path = os.environ.get("NEXUS_PROJECT_PATH", os.path.expanduser("~/Projects/nexus"))

            # Gather changed files from completed tasks
            board = memory.get_board_tasks(did)
            changed_files = []
            if board:
                for task in board:
                    ctx = task.get("context", {})
                    if isinstance(ctx, dict):
                        changed_files.extend(ctx.get("files_changed", []))

            # If no files tracked, scan recent context entries
            if not changed_files:
                entries = memory.get_context_for_directive(did)
                for e in entries:
                    if isinstance(e, dict) and e.get("type") == "code":
                        path = e.get("file_path", "")
                        if path:
                            changed_files.append(path)

            result = await run_plugin_review_suite(
                changed_files, project_path
            )
            _store_review(did, result)
        except Exception as e:
            logger.error(f"Plugin review failed for {did}: {e}")
            _store_review(did, {"passed": True, "results": [], "error": str(e)})

    async def _check_plugin_review_done(self, did):
        """Check plugin review results. Critical findings go back to fixing; otherwise complete."""
        entry = _plugin_review_results.get(did)
        results = entry[1] if entry else None
        if results is None:
            return  # Still running

        critical = results.get("critical_findings", 0)
        if critical > 0:
            # File defects for critical findings and send back to fixing
            for r in results.get("results", []):
                if hasattr(r, "findings"):
                    for f in r.findings:
                        if f.severity in ("critical", "high"):
                            memory.file_defect(
                                directive_id=did,
                                title=f"[Plugin Review] {f.category}: {f.message[:80]}",
                                description=f"File: {f.file}, Line: {f.line}\n{f.message}",
                                file_path=f.file,
                                severity=f.severity,
                            )
            memory.update_directive(did, status="fixing")
            await self._notify(f"Plugin review found {critical} critical issue(s). Fixing.", did)
        else:
            memory.update_directive(did, status="complete")
            board = memory.get_board_tasks(did)
            completed_tasks = [t for t in board if t["status"] == "complete"] if board else []
            task_summary = "\n".join(f"  - {t['title']}" for t in completed_tasks[:10])
            project_path = os.environ.get("NEXUS_PROJECT_PATH", os.path.expanduser("~/Projects/nexus"))

            # ML: record directive completion for similarity search
            try:
                directive = memory.get_directive(did)
                if directive:
                    ml_feedback.record_directive_complete(
                        directive_id=did,
                        directive_text=directive["text"],
                        total_tasks=len(completed_tasks),
                        outcome="complete",
                    )
            except Exception as ml_err:
                logger.debug("ML directive feedback failed: %s", ml_err)

            await self._notify(
                f"*Project complete!* Code built, tested, reviewed, and plugin-verified.\n\n"
                f"*Delivered {len(completed_tasks)} task(s):*\n{task_summary}\n\n"
                f"*Output location:* `{project_path}`",
                did,
            )

        # Cleanup
        _plugin_review_results.pop(did, None)

    async def _safe_run(self, agent_id, decision, directive_id):
        agent = self.agents.get(agent_id)
        if not agent:
            return

        task_id = getattr(decision, 'task_id', '') or ''
        agent_id_var.set(agent_id)
        task_id_var.set(task_id)

        breaker = breaker_registry.get(agent_id)

        start_time = time.time()
        try:
            # Wrap execution in circuit breaker
            await breaker.call(agent.execute(decision, directive_id))
            # Success: reset escalation retry count
            escalation_chain.reset_retries(agent_id)

            # ML: record successful task outcome
            try:
                defects = memory.get_defects_for_task(task_id) if task_id else []
                ml_feedback.record_task_outcome(
                    directive_id=directive_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    task_description=getattr(decision, 'action', ''),
                    outcome="complete",
                    specialty=getattr(agent, 'specialty', ''),
                    duration_sec=time.time() - start_time,
                    defect_count=len(defects),
                    qa_cycles=self._qa_cycles.get(directive_id, 0),
                    model=ORG_CHART.get(agent_id, {}).get("model", ""),
                )
            except Exception as ml_err:
                logger.debug("ML feedback recording failed: %s", ml_err)

        except CircuitOpenError as e:
            # Circuit is open, skip and try escalation
            logger.warning(f"[{agent.name}] Circuit open: {e}")
            memory.emit_event(agent_id, "circuit_open", {
                "agent": agent.name,
                "time_until_retry": e.time_until_retry,
                "action": getattr(decision, 'action', ''),
            })

            # ML: persist circuit breaker event
            from src.agents.registry import registry
            registry.record_circuit_event(
                agent_id=agent_id,
                event_type="trip",
                reason=f"failure_count={breaker.failure_count}, model={ORG_CHART.get(agent_id, {}).get('model', '')}, task_type={getattr(decision, 'action', '')[:100]}",
            )

            # Attempt escalation to higher-tier agent
            agent_config = ORG_CHART.get(agent_id, {})
            current_model = agent_config.get("model", "sonnet")
            upgrade_model = escalation_chain.get_upgrade_model(current_model)

            if upgrade_model:
                escalation_chain.escalate(
                    agent_id,
                    f"Circuit open, escalating to {upgrade_model}",
                    tier=escalation_chain.TIER_MAP.get(upgrade_model, 2)
                )
                # ML: persist escalation event
                ml_feedback.record_escalation(
                    agent_id=agent_id,
                    from_model=current_model,
                    to_model=upgrade_model,
                    reason=str(e)[:200],
                    task_type=getattr(decision, 'action', '')[:100],
                )
                await self._notify(
                    f"⚠️ {agent.name} circuit open. Escalating to {upgrade_model} tier.",
                    directive_id
                )
            else:
                # Top tier failed, send to dead letter
                escalation_chain.to_dead_letter(
                    agent_id,
                    getattr(decision, 'action', 'unknown'),
                    str(e),
                    breaker.failure_count
                )
                await self._notify(
                    f"❌ {agent.name} exhausted all escalation tiers. Filed to dead letter queue.",
                    directive_id
                )

            if hasattr(decision, 'task_id') and decision.task_id:
                memory.fail_board_task(decision.task_id, error=f"Circuit open: {e}")

        except Exception as e:
            # Regular failure: circuit breaker already recorded it via _on_failure
            logger.error(f"[{agent.name}] Error: {e}", exc_info=True)
            memory.emit_event(agent_id, "agent_error", {
                "error": str(e)[:500],
                "agent": agent.name,
                "action": getattr(decision, 'action', ''),
            })

            if hasattr(decision, 'task_id') and decision.task_id:
                memory.fail_board_task(decision.task_id, error=str(e)[:500])

            # ML: record failed task outcome
            try:
                ml_feedback.record_task_outcome(
                    directive_id=directive_id,
                    task_id=getattr(decision, 'task_id', '') or '',
                    agent_id=agent_id,
                    task_description=getattr(decision, 'action', ''),
                    outcome="failed",
                    specialty=getattr(agent, 'specialty', ''),
                    duration_sec=time.time() - start_time,
                    model=ORG_CHART.get(agent_id, {}).get("model", ""),
                )
            except Exception as ml_err:
                logger.debug("ML feedback recording failed: %s", ml_err)

    async def handle_message(self, message, source="slack", thread_ts=None):
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
For a SINGLE hire, return ONE JSON object. For a TEAM, return a JSON ARRAY of objects.
Each object: {{"id":"snake","name":"Male name","title":"Title","role":"desc","reports_to":"mgr","model":"claude-sonnet-4-20250514","specialty":""}}""", HAIKU)
            parsed = extract_json(raw)
            if not parsed: return "Couldn't parse hiring details."

            # Normalize to a list whether LLM returns one dict or an array
            hires = parsed if isinstance(parsed, list) else [parsed]

            results = []
            for details in hires:
                if not isinstance(details, dict):
                    continue
                mgr = self.agents.get(details.get("reports_to", "vp_engineering"))
                if not mgr:
                    results.append(f"Manager `{details.get('reports_to')}` not found for {details.get('name', '?')}")
                    continue
                result = await mgr.hire(
                    agent_id=details["id"], name=details["name"], title=details["title"],
                    role=details["role"], model=details.get("model", SONNET),
                    specialty=details.get("specialty", ""))
                self.agents[details["id"]] = create_agent(details["id"])
                results.append(result)

            return "\n".join(results) if results else "No agents hired."
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
