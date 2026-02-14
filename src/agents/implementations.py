"""
NEXUS Agent Implementations v3.0 — Full Autonomy

- Engineers: code, defend designs, take feedback, fix defects
- PMs: feed context to engineers, gather requirements, shield from noise
- QA: test immediately, file real defect artifacts, reject bad code
- VPs: orchestrate, hire for gaps, make fast decisions
- Peers: when unsure, consult a peer, decide fast, execute immediately
- CEO: directives and firing. That's it.
"""

import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime

from src.agents.base import Agent
from src.agents.registry import registry
from src.memory.store import memory

logger = logging.getLogger("nexus.agent")


def extract_json(text: str) -> dict | list | None:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass
    for pattern in [r'```json\s*\n?(.*?)```', r'```\s*\n?(.*?)```']:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                continue
    for open_c, close_c in [('{', '}'), ('[', ']')]:
        first = text.find(open_c)
        last = text.rfind(close_c)
        if first != -1 and last > first:
            try:
                return json.loads(text[first:last + 1])  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                continue
    return None


async def peer_consult(agent_a: Agent, agent_b_id: str, question: str,
                        directive_id: str) -> str:
    """Two agents consult on a question and reach a fast decision."""
    agent_b = registry.get_agent(agent_b_id)
    b_name = agent_b.name if agent_b else agent_b_id
    b_role = agent_b.description if agent_b else "colleague"

    prompt = f"""You are {agent_a.name} ({agent_a.title}).
You're consulting with {b_name} ({b_role}) on this question:

"{question}"

Think through it quickly, make a decision, and state it clearly.
Be decisive — don't waffle. One paragraph max.

Your decision:"""

    response = await agent_a.think(prompt, max_tokens=500)

    memory.record_peer_decision(
        directive_id=directive_id,
        participants=[agent_a.agent_id, agent_b_id],
        question=question,
        decision=response[:500],
    )

    return response


# ---------------------------------------------------------------------------
# Stub
# ---------------------------------------------------------------------------
class StubAgent(Agent):
    async def do_work(self, decision, directive_id):
        return f"{self.name}: ready"


# ---------------------------------------------------------------------------
# PM — feeds engineers context, gathers requirements, shields from noise
# ---------------------------------------------------------------------------
class PMAgent(Agent):
    async def do_work(self, decision, directive_id):
        directive = memory.get_directive(directive_id)
        if not directive:
            return "No directive"

        # Check if there are tasks missing context
        board = memory.get_board_tasks(directive_id)
        tasks_needing_context = [t for t in board if t["status"] == "available"
                                  and len(t.get("description", "")) < 50]

        if tasks_needing_context:
            # Enrich tasks with detailed requirements
            for task in tasks_needing_context[:3]:
                enriched = await self.think(f"""You are a PM. Enrich this task with specific, actionable requirements.

Directive: "{directive['text']}"
Task: "{task['title']}"
Current description: "{task.get('description', '')}"

Write a clear, detailed description (3-5 sentences) that an engineer can code from immediately.
Include: expected behavior, edge cases to handle, any UI/UX specifics.
Plain text only. No JSON.""", max_tokens=400)

                memory._conn.cursor().execute(
                    "UPDATE task_board SET description=?,updated_at=? WHERE id=?",
                    (enriched.strip(), datetime.now(UTC).isoformat(), task["id"]))
                memory._conn.commit()
                logger.info(f"[{self.name}] Enriched task: {task['title']}")

            return f"Enriched {len(tasks_needing_context)} tasks with requirements"

        # Check for open defects — add context for engineers fixing them
        defects = memory.get_open_defects(directive_id)
        if defects:
            for defect in defects[:2]:
                if not defect.get("assigned_to"):
                    # Assign to appropriate engineer
                    desc = defect.get("description", "").lower()
                    if any(w in desc for w in ["frontend", "ui", "css", "react", "html"]):
                        memory.assign_defect(defect["id"], "fe_engineer_1")
                    else:
                        memory.assign_defect(defect["id"], "be_engineer_1")
            return f"Triaged {len(defects)} defects"

        return "All tasks enriched, no defects to triage"


# ---------------------------------------------------------------------------
# VP Product — only writes strategy when asked
# ---------------------------------------------------------------------------
class VPProductAgent(Agent):
    async def do_work(self, decision, directive_id):
        directive = memory.get_directive(directive_id)
        if not directive:
            return "No directive"

        text = directive["text"].lower()
        if any(w in text for w in ["memo", "strategy", "prd", "plan", "requirements", "spec"]):
            existing = memory.get_latest_context(directive_id, "product_strategy")
            if existing:
                return "Already delivered"
            plan = await self.think(f"""CEO said: "{directive['text']}"
Concise product strategy. Under 500 words. Actionable. Include: what, who, v1 scope, 3 success metrics.""", max_tokens=1500)
            memory.post_context(self.agent_id, "product_strategy", plan, directive_id)
            return "Strategy delivered"

        return "No strategy requested — team is building"


# ---------------------------------------------------------------------------
# VP Engineering — orchestrates, hires for gaps, unblocks
# ---------------------------------------------------------------------------
class VPEngineeringAgent(Agent):
    async def do_work(self, decision, directive_id):
        directive = memory.get_directive(directive_id)
        if not directive:
            return "No directive"

        board = memory.get_board_tasks(directive_id)
        failed = [t for t in board if t["status"] == "failed"]
        _defects = memory.get_open_defects(directive_id)

        actions = []

        # Check for persistent failures → skill gap → hire
        if len(failed) >= 3:
            gap = await self._assess_skill_gap(
                " | ".join(t.get("description", "")[:100] for t in failed[:3]))
            if gap:
                try:
                    await self.hire(
                        agent_id=f"hired_{gap['id']}",
                        name=gap["name"], title=gap["title"],
                        role=gap["role"], specialty=gap.get("specialty", ""))
                    actions.append(f"Hired {gap['name']} for skill gap")
                except Exception as e:
                    actions.append(f"Hire failed: {e}")

        # Reset stuck tasks
        for task in failed:
            memory.reset_board_task(task["id"])
            actions.append(f"Reset failed task: {task['title']}")

        if not actions:
            actions.append("Engineering running smoothly")

        return "; ".join(actions)

    async def _assess_skill_gap(self, context: str) -> dict | None:
        try:
            raw = await self.think(f"""Tasks keep failing: "{context}"
Our team: React/TS frontend, Python/FastAPI/Node backend, DevOps.
Skill gap? JSON: {{"gap":true,"id":"short","name":"Male name","title":"Title","role":"desc","specialty":"area"}} or {{"gap":false}}""", max_tokens=300)
            data = extract_json(raw)
            return data if data and isinstance(data, dict) and data.get("gap") else None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Chief Architect — quick guidance, not a thesis
# ---------------------------------------------------------------------------
class ChiefArchitectAgent(Agent):
    async def do_work(self, decision, directive_id):
        existing = memory.get_latest_context(directive_id, "architecture")
        if existing:
            return "Architecture posted"

        directive = memory.get_directive(directive_id)
        design = await self.think(f"""Quick architecture for: "{directive['text']}"
Simple. v1. Practical. JSON: {{"stack":"tech","structure":["files"],"notes":"2-3 sentences"}}""", max_tokens=1500)
        memory.post_context(self.agent_id, "architecture", design, directive_id)
        return "Architecture posted"


# ---------------------------------------------------------------------------
# Engineer — writes code, fixes defects, defends designs
# ---------------------------------------------------------------------------
class EngineerAgent(Agent):

    async def do_work(self, decision, directive_id):
        directive = memory.get_directive(directive_id)
        project_path = directive.get("project_path", "") or os.path.expanduser("~/Projects/nexus-output")

        # Priority 1: Fix assigned defects
        defects = self._get_my_defects(directive_id)
        if defects:
            return await self._fix_defect(defects[0], directive, project_path)

        # Priority 2: Build assigned task
        task = self._get_task(decision)
        if not task:
            return "No task assigned"

        return await self._build_task(task, directive, project_path)

    def _get_my_defects(self, directive_id):
        defects = memory.get_open_defects(directive_id)
        return [d for d in defects if d.get("assigned_to") == self.agent_id]

    def _get_task(self, decision):
        if not decision.task_id:
            return None
        c = memory._conn.cursor()
        c.execute("SELECT * FROM task_board WHERE id=?", (decision.task_id,))
        row = c.fetchone()
        return dict(row) if row else None

    async def _fix_defect(self, defect, directive, project_path):
        """Fix a defect filed by QA."""
        # Read the existing file if it exists
        existing_code = ""
        if defect.get("file_path"):
            full_path = os.path.join(project_path, defect["file_path"])
            if os.path.exists(full_path):
                with open(full_path) as f:
                    existing_code = f.read()

        response = await self.think(f"""You are {self.name}. Fix this defect.

DEFECT: {defect['title']}
Description: {defect['description']}
Severity: {defect['severity']}
File: {defect.get('file_path', 'unknown')}

{f"EXISTING CODE:{chr(10)}{existing_code[:3000]}" if existing_code else ""}

Write the FIXED version of the file.
JSON: {{"files": [{{"path": "path", "content": "full fixed content"}}], "summary": "what was fixed"}}""", max_tokens=8192)

        data = extract_json(response)
        if data and "files" in data:
            for fi in data["files"]:
                fpath = fi.get("path", defect.get("file_path", ""))
                content = fi.get("content", "")
                if fpath and content:
                    full_path = os.path.join(project_path, fpath)
                    os.makedirs(os.path.dirname(full_path) or project_path, exist_ok=True)
                    with open(full_path, "w") as f:
                        f.write(content)

            memory.resolve_defect(defect["id"], self.agent_id)
            summary = data.get("summary", f"Fixed: {defect['title']}")
            memory.post_context(self.agent_id, "defect_fix",
                json.dumps({"defect": defect["id"], "summary": summary}), directive.get("id", ""))
            return f"Fixed defect: {summary}"

        return f"Attempted fix for {defect['title']} (parse failed)"

    async def _build_task(self, task, directive, project_path):
        """Build a task — write real files."""
        arch = memory.get_latest_context(directive["id"], "architecture")
        feedback = memory.get_latest_context(directive["id"], "feedback")

        # See what others have built
        code_entries = memory.get_context_for_directive(directive["id"])
        peer_code = ""
        for e in code_entries[-5:]:
            if e["type"] == "code" and e["author"] != self.agent_id:
                peer_code += f"\n[{e['author']}]: {str(e['content'])[:300]}"

        response = await self.think(f"""You are {self.name}, {self.title}. {f"Specialty: {self.specialty}" if self.specialty else ""}

TASK: {task['title']}
DESCRIPTION: {task.get('description', 'No details')}
DIRECTIVE: {directive['text']}
{f"ARCHITECTURE: {arch['content'][:1500]}" if arch else ""}
{f"PEER CODE: {peer_code}" if peer_code else ""}
{f"CEO FEEDBACK: {feedback['content'][:500]}" if feedback else ""}

Write COMPLETE, WORKING code.
JSON: {{"files": [{{"path": "path", "content": "FULL content"}}], "summary": "one line"}}
Rules: complete files, error handling, comments explain WHY. JSON ONLY.""", max_tokens=8192)

        data = extract_json(response)
        if data and "files" in data:
            written = []
            for fi in data["files"]:
                fpath = fi.get("path", "")
                content = fi.get("content", "")
                if fpath and content:
                    full_path = os.path.join(project_path, fpath)
                    os.makedirs(os.path.dirname(full_path) or project_path, exist_ok=True)
                    with open(full_path, "w") as f:
                        f.write(content)
                    written.append(fpath)

            summary = data.get("summary", f"Wrote {len(written)} files")
            memory.post_context(self.agent_id, "code",
                json.dumps({"files": written, "summary": summary, "task": task["id"]}),
                directive["id"])
            return f"{summary} ({', '.join(written)})"

        memory.post_context(self.agent_id, "code", response[:2000], directive["id"])
        return f"Code written (raw): {task['title']}"


# ---------------------------------------------------------------------------
# QA — tests immediately, files real defect artifacts
# ---------------------------------------------------------------------------
class QAAgent(Agent):

    async def do_work(self, decision, directive_id):
        directive = memory.get_directive(directive_id)
        if not directive:
            return "No directive"

        project_path = directive.get("project_path", "") or os.path.expanduser("~/Projects/nexus-output")

        # Find recently completed code to review
        code_entries = memory.get_context_for_directive(directive_id)
        code_to_review = [e for e in code_entries if e["type"] == "code"
                          and e["author"] != self.agent_id]

        if not code_to_review:
            return "No code to review yet"

        latest = code_to_review[-1]
        code_data = extract_json(latest["content"]) if isinstance(latest["content"], str) else latest["content"]

        if not code_data or not isinstance(code_data, dict):
            return "Code entry not parseable"

        files = code_data.get("files", [])
        if not files:
            return "No files to test"

        # Read each file and review
        defects_filed = 0
        for fpath in files[:5]:
            full_path = os.path.join(project_path, fpath) if isinstance(fpath, str) else ""
            if not full_path or not os.path.exists(full_path):
                continue

            with open(full_path) as f:
                code = f.read()

            if len(code.strip()) < 10:
                continue

            review = await self.think(f"""You are {self.name}, {self.title}. Review this code for defects.

FILE: {fpath}
```
{code[:4000]}
```

Check for:
1. Bugs (logic errors, off-by-one, null handling, missing error handling)
2. Security issues (XSS, injection, hardcoded secrets)
3. Missing functionality (based on what the code claims to do)
4. Integration issues (broken imports, wrong paths)

If there are defects, respond with JSON:
{{"defects": [{{"title": "brief title", "description": "what's wrong and how to fix it", "severity": "critical/high/medium/low", "line": 0}}]}}

If the code is acceptable: {{"defects": []}}
JSON ONLY.""", max_tokens=1500)

            data = extract_json(review)
            if data and data.get("defects"):
                for defect in data["defects"]:
                    defect_id = f"defect-{uuid.uuid4().hex[:8]}"
                    memory.create_defect(
                        defect_id=defect_id,
                        directive_id=directive_id,
                        task_id=code_data.get("task", ""),
                        title=defect.get("title", "Unnamed defect"),
                        description=defect.get("description", ""),
                        severity=defect.get("severity", "medium"),
                        filed_by=self.agent_id,
                        file_path=fpath,
                        line_number=defect.get("line", 0),
                    )
                    defects_filed += 1
                    logger.info(f"[{self.name}] Filed defect: {defect.get('title', '?')}")

        if defects_filed > 0:
            memory.post_context(self.agent_id, "qa_review",
                json.dumps({"defects_filed": defects_filed, "files_reviewed": len(files)}),
                directive_id)
            return f"Filed {defects_filed} defect(s)"
        else:
            memory.post_context(self.agent_id, "qa_review",
                json.dumps({"status": "passed", "files_reviewed": len(files)}),
                directive_id)
            return f"Code passed QA ({len(files)} files reviewed)"


# ---------------------------------------------------------------------------
# Architect — final authority on all code changes (ARCH-010)
# ---------------------------------------------------------------------------
class ArchitectAgent(Agent):
    """Final authority on all code changes. Reviews for architecture compliance.

    The Architect agent has veto power over ANY change. This is an agent-to-agent
    approval gate — no user prompts involved.
    """

    async def do_work(self, decision, directive_id):
        directive = memory.get_directive(directive_id)
        if not directive:
            return "No directive"
        return await self.review_changes({"directive_id": directive_id})

    async def review_changes(self, context: dict) -> dict:
        """Review all changes for architecture soundness, security, performance, quality.

        Returns: {approved: bool, feedback: str, required_changes: list}
        """
        directive_id = context.get("directive_id", "")
        directive = memory.get_directive(directive_id) if directive_id else None

        # Gather all context for review
        code_entries = memory.get_context_for_directive(directive_id) if directive_id else []
        code_summaries = []
        for e in code_entries[-10:]:
            if e["type"] in ("code", "defect_fix"):
                code_summaries.append(f"[{e['author']}] {str(e['content'])[:500]}")

        arch_context = memory.get_latest_context(directive_id, "architecture") if directive_id else None
        qa_reviews = [e for e in code_entries if e["type"] == "qa_review"]

        review_prompt = f"""You are the Chief Architect with FINAL AUTHORITY on all code changes.
Review the following for architecture compliance. Be decisive.

DIRECTIVE: {directive['text'] if directive else 'Unknown'}
{f"ARCHITECTURE: {arch_context['content'][:1500]}" if arch_context else "No architecture doc found."}

CODE CHANGES:
{chr(10).join(code_summaries) if code_summaries else "No code changes found."}

QA RESULTS:
{chr(10).join(str(e['content'])[:300] for e in qa_reviews[-3:]) if qa_reviews else "No QA results."}

Evaluate:
1. Architecture soundness — does the code follow the approved design?
2. Security — any vulnerabilities or trust boundary violations?
3. Performance — any obvious bottlenecks or anti-patterns?
4. Quality — maintainability, readability, error handling?

JSON response:
{{"approved": true/false, "feedback": "brief overall assessment", "required_changes": ["change1", "change2"]}}
If approved, required_changes should be empty.
JSON ONLY."""

        response = await self.think(review_prompt, max_tokens=1500)
        data = extract_json(response)

        if data and isinstance(data, dict):
            approved = bool(data.get("approved", False))
            feedback = data.get("feedback", "No feedback provided")
            required_changes = data.get("required_changes", [])

            memory.post_context(
                self.agent_id,
                "architect_review",
                json.dumps({
                    "approved": approved,
                    "feedback": feedback,
                    "required_changes": required_changes,
                }),
                directive_id,
            )

            return {
                "approved": approved,
                "feedback": feedback,
                "required_changes": required_changes,
            }

        # Parse failure — reject to be safe
        return {
            "approved": False,
            "feedback": "Architect review could not be parsed. Rejecting for safety.",
            "required_changes": ["Retry architect review"],
        }


# ---------------------------------------------------------------------------
# Code Reviewer — reviews code quality, not bugs (that's QA)
# ---------------------------------------------------------------------------
class CodeReviewAgent(Agent):
    async def do_work(self, decision, directive_id):
        directive = memory.get_directive(directive_id)
        project_path = directive.get("project_path", "") or os.path.expanduser("~/Projects/nexus-output")

        code_entries = memory.get_context_for_directive(directive_id)
        code_to_review = [e for e in code_entries if e["type"] == "code"]

        if not code_to_review:
            return "Nothing to review"

        latest = code_to_review[-1]
        code_data = extract_json(latest["content"]) if isinstance(latest["content"], str) else latest["content"]
        if not code_data or not isinstance(code_data, dict):
            return "Not parseable"

        files = code_data.get("files", [])
        for fpath in files[:3]:
            full_path = os.path.join(project_path, fpath) if isinstance(fpath, str) else ""
            if not full_path or not os.path.exists(full_path):
                continue

            with open(full_path) as f:
                code = f.read()

            review = await self.think(f"""Review this code for quality. Focus on:
- Maintainability, readability, naming
- Architecture alignment
- Performance red flags
- Comments that explain WHY

FILE: {fpath}
```
{code[:4000]}
```

If there are serious issues that should be fixed, file defects. Otherwise approve.
JSON: {{"approved": true/false, "feedback": "brief note", "defects": [...]}}""", max_tokens=1000)

            data = extract_json(review)
            if data and data.get("defects"):
                for d in data["defects"]:
                    defect_id = f"cr-{uuid.uuid4().hex[:8]}"
                    memory.create_defect(
                        defect_id=defect_id, directive_id=directive_id,
                        task_id=code_data.get("task", ""),
                        title=d.get("title", "Code review issue"),
                        description=d.get("description", ""),
                        severity=d.get("severity", "medium"),
                        filed_by=self.agent_id, file_path=fpath)

        return f"Reviewed {len(files)} files"


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------
class CoordinatorAgent(Agent):
    async def do_work(self, decision, directive_id):
        board = memory.get_board_tasks(directive_id)
        defects = memory.get_open_defects(directive_id)
        return {
            "tasks": len(board),
            "complete": sum(1 for t in board if t["status"] == "complete"),
            "defects_open": len(defects),
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
AGENT_CLASSES = {
    "vp_product": VPProductAgent,
    "pm_1": PMAgent,
    "pm_2": PMAgent,
    "vp_engineering": VPEngineeringAgent,
    "chief_architect": ChiefArchitectAgent,
    "architect": ArchitectAgent,
    "eng_lead": StubAgent,
    "fe_engineer_1": EngineerAgent,
    "fe_engineer_2": EngineerAgent,
    "be_engineer_1": EngineerAgent,
    "be_engineer_2": EngineerAgent,
    "code_review_lead": CodeReviewAgent,
    "fe_reviewer": CodeReviewAgent,
    "be_reviewer": CodeReviewAgent,
    "qa_lead": QAAgent,
    "fe_tester": QAAgent,
    "be_tester": QAAgent,
    "unit_test_engineer": StubAgent,
    "ciso": StubAgent,
    "security_engineer": StubAgent,
    "devops_engineer": StubAgent,
    "head_of_docs": StubAgent,
    "tech_writer": StubAgent,
    "consultant": StubAgent,
    "director_analytics": StubAgent,
    "sr_data_analyst": StubAgent,
    "data_analyst": StubAgent,
}


def create_agent(agent_id: str) -> Agent:
    cls = AGENT_CLASSES.get(agent_id, StubAgent)
    return cls(agent_id)  # type: ignore[abstract]


def create_all_agents() -> dict[str, Agent]:
    agents = {}
    for agent in registry.get_active_agents():
        agent_obj = create_agent(agent.id)
        agent_obj.register()
        agents[agent.id] = agent_obj
    return agents
