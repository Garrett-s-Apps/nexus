"""
NEXUS Task Runner

Persistent, autonomous task execution. Tasks survive server restarts.

Key features:
- Tasks are persisted to SQLite before execution starts
- Each step is checkpointed — resume from where it left off
- Failed steps retry up to 3 times
- Progress reported to Slack throughout
- Server startup resumes any interrupted tasks
"""

import os
import json
import asyncio
import anthropic
import traceback
from datetime import datetime
from typing import Any

from src.memory.store import memory
from src.slack.notifier import notify, notify_escalation


RETRY_LIMIT = 3


def _load_key(key_name: str) -> str | None:
    try:
        with open(os.path.expanduser("~/.nexus/.env.keys")) as f:
            for line in f:
                line = line.strip()
                if line.startswith(key_name + "="):
                    return line.split("=", 1)[1]
    except FileNotFoundError:
        pass
    return os.environ.get(key_name)


def _get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=_load_key("ANTHROPIC_API_KEY"))


async def run_task(task_id: str, directive: str, project_path: str, project_id: str = ""):
    """
    Execute a build task with persistent checkpointing.
    Each phase saves progress so it can resume if interrupted.
    """
    client = _get_client()
    total_cost = 0.0

    # Create persistent task record
    task = memory.get_task(task_id)
    if not task:
        memory.create_task(task_id, directive, project_path, project_id)
        task = memory.get_task(task_id)

    progress = json.loads(task.get("progress", "{}") or "{}")

    def _update(status: str = None, step: str = None, **kwargs):
        nonlocal total_cost
        memory.update_task(
            task_id,
            status=status,
            current_step=step,
            progress={**progress, **kwargs},
            cost=total_cost,
        )

    def _log(msg: str):
        print(f"[Task {task_id[:8]}] {msg}")

    try:
        memory.update_task(task_id, status="running")

        # ============================================
        # PHASE 1: PLAN (skip if already done)
        # ============================================
        if "plan" not in progress:
            _update(step="planning")
            notify(f"Planning: _{directive[:80]}_")
            _log("Phase 1: Planning...")

            plan = await _plan_with_retry(client, directive, project_path)
            if not plan:
                _update(status="error", step="planning_failed")
                notify(f"*Planning failed* for: {directive[:60]}")
                return

            total_cost += plan.get("_cost", 0)
            progress["plan"] = plan
            _update(step="plan_complete", plan=plan)
            _log(f"Plan ready: {plan.get('summary', 'N/A')} — {len(plan.get('files', []))} files")
            notify(f"Plan ready: *{plan.get('summary', directive[:60])}*\n{len(plan.get('files', []))} files to create")
        else:
            plan = progress["plan"]
            _log(f"Resuming from existing plan: {plan.get('summary', 'N/A')}")

        # ============================================
        # PHASE 2: BUILD (resume from last completed file)
        # ============================================
        _update(step="building")
        completed_files = progress.get("completed_files", [])
        all_files = plan.get("build_order", [f["path"] for f in plan.get("files", [])])
        file_map = {f["path"]: f for f in plan.get("files", [])}
        written_context = progress.get("written_context", {})

        for file_path in all_files:
            if file_path in completed_files:
                _log(f"Skipping {file_path} (already done)")
                continue

            _log(f"Building: {file_path}")
            _update(step=f"building:{file_path}")

            file_info = file_map.get(file_path, {"path": file_path, "purpose": "", "language": ""})

            content = await _build_file_with_retry(
                client, file_path, file_info, plan, directive, project_path, written_context
            )

            if content is None:
                _update(status="error", step=f"build_failed:{file_path}")
                notify(f"*Build failed* on `{file_path}`")
                notify_escalation("task_runner", f"Failed to build {file_path} for: {directive[:60]}")
                return

            total_cost += content.get("_cost", 0)

            # Write file
            full_path = os.path.join(project_path, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content["code"])

            completed_files.append(file_path)
            written_context[file_path] = content["code"][:2000]  # Keep truncated for context
            progress["completed_files"] = completed_files
            progress["written_context"] = written_context
            _update(completed_files=completed_files, written_context=written_context)
            _log(f"Created {file_path} ({len(content['code'])} bytes)")

        notify(f"Code written: {len(completed_files)} files.\nRunning QA...")

        # ============================================
        # PHASE 3: QA
        # ============================================
        if "qa" not in progress:
            _update(step="qa")
            _log("Phase 3: QA review...")

            qa_result = await _qa_with_retry(client, written_context)
            total_cost += qa_result.get("_cost", 0)
            progress["qa"] = qa_result.get("verdict", "unknown")
            _update(qa=progress["qa"])
            _log(f"QA verdict: {progress['qa']}")

        # ============================================
        # PHASE 4: GIT
        # ============================================
        commit_sha = None
        branch_name = None
        if "git" not in progress and os.path.exists(os.path.join(project_path, ".git")):
            _update(step="git")
            try:
                from src.git_ops.git import GitOps
                git = GitOps(project_path)
                branch_name = git.create_feature_branch(directive[:30])
                git.stage_files(completed_files)
                commit_sha = git.commit(f"feat: {directive[:60]}", cost=total_cost)
                progress["git"] = {"branch": branch_name, "commit": commit_sha}
                _update(git=progress["git"])
                _log(f"Committed {commit_sha} on {branch_name}")
            except Exception as e:
                _log(f"Git failed (non-fatal): {e}")

        # ============================================
        # PHASE 5: COMPLETE
        # ============================================
        _update(status="complete", step="done")

        report = f"""*Build Complete: {plan.get('summary', directive[:60])}*

Files created: {len(completed_files)}
{chr(10).join(f'  • {f}' for f in completed_files)}

Tech stack: {plan.get('tech_stack', 'N/A')}
QA verdict: {progress.get('qa', 'N/A')}
Total cost: ${total_cost:.4f}"""

        if branch_name:
            report += f"\nBranch: `{branch_name}`"
        if commit_sha:
            report += f"\nCommit: `{commit_sha[:8]}`"

        notify(report)

        # Update project if linked
        if project_id:
            memory.update_project_status(project_id, "built", cost=total_cost)
            memory.add_project_note(project_id, f"Built: {len(completed_files)} files, ${total_cost:.4f}", "execution")

        # Track KPI
        from src.kpi.tracker import kpi_tracker
        kpi_tracker.record_task_completion("task_runner", directive[:100], total_cost, 0)

        _log(f"Task complete. Cost: ${total_cost:.4f}")
        return {"status": "complete", "files": completed_files, "cost": total_cost}

    except Exception as e:
        tb = traceback.format_exc()
        _log(f"Task failed: {e}\n{tb}")
        memory.update_task(task_id, status="error", error=str(e))
        notify_escalation("task_runner", f"Task failed: {str(e)[:200]}")
        return {"status": "error", "error": str(e)}


async def _plan_with_retry(client, directive, project_path, retries=RETRY_LIMIT) -> dict | None:
    """Plan the build with retries."""
    for attempt in range(retries):
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=f"""You are the VP of Engineering at Nexus. Create a build plan.
Project directory: {project_path}
Output valid JSON only. Be practical — fewer files is better.""",
                messages=[{"role": "user", "content": f"""Directive: {directive}

Create a build plan as JSON:
{{
    "summary": "one line description",
    "tech_stack": "languages and frameworks",
    "files": [
        {{"path": "relative/path/to/file.ext", "purpose": "what this file does", "language": "python|typescript|html|etc"}}
    ],
    "build_order": ["file paths in creation order"],
    "test_strategy": "how to verify"
}}

Only return JSON."""}],
            )

            text = response.content[0].text.strip()
            cost = 0.0
            if response.usage:
                from src.cost.tracker import cost_tracker
                cost_tracker.record("sonnet", "vp_engineering", response.usage.input_tokens, response.usage.output_tokens)
                cost = cost_tracker.calculate_cost("sonnet", response.usage.input_tokens, response.usage.output_tokens)

            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.rstrip().endswith("```"):
                text = text.rstrip().rsplit("```", 1)[0]

            plan = json.loads(text.strip())
            plan["_cost"] = cost
            return plan

        except Exception as e:
            print(f"[TaskRunner] Plan attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    return None


async def _build_file_with_retry(client, file_path, file_info, plan, directive, project_path, written_context, retries=RETRY_LIMIT) -> dict | None:
    """Build a single file with retries."""
    context_str = ""
    if written_context:
        context_str = "\n\nAlready written files:\n"
        for wp, wc in list(written_context.items())[-5:]:  # Last 5 files for context
            context_str += f"\n--- {wp} ---\n{wc}\n"

    for attempt in range(retries):
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                system=f"""You are a senior engineer at Nexus. Write production-quality code.
Project: {project_path}
RULES: Complete working code. No placeholders. No TODOs. Handle errors. No hardcoded secrets.
Output ONLY file contents. No markdown fences, no explanation.""",
                messages=[{"role": "user", "content": f"""Write this file:
Path: {file_path}
Purpose: {file_info.get('purpose', '')}
Language: {file_info.get('language', '')}
Project: {plan.get('summary', directive)}
Stack: {plan.get('tech_stack', '')}
{context_str}

Write the complete file now."""}],
            )

            code = response.content[0].text
            cost = 0.0
            if response.usage:
                from src.cost.tracker import cost_tracker
                cost_tracker.record("sonnet", "implementation", response.usage.input_tokens, response.usage.output_tokens)
                cost = cost_tracker.calculate_cost("sonnet", response.usage.input_tokens, response.usage.output_tokens)

            if code.startswith("```"):
                code = code.split("\n", 1)[1]
            if code.rstrip().endswith("```"):
                code = code.rstrip().rsplit("```", 1)[0]

            return {"code": code, "_cost": cost}

        except Exception as e:
            print(f"[TaskRunner] Build {file_path} attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
    return None


async def _qa_with_retry(client, written_context, retries=RETRY_LIMIT) -> dict:
    """QA review with retries."""
    all_code = ""
    for fp, fc in written_context.items():
        all_code += f"\n=== {fp} ===\n{fc}"

    for attempt in range(retries):
        try:
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system="QA lead. Quick review. Critical issues only. Be brief.",
                messages=[{"role": "user", "content": f"Review:\n{all_code[:15000]}\n\nVerdict: SHIP IT or NEEDS FIXES?"}],
            )

            cost = 0.0
            if response.usage:
                from src.cost.tracker import cost_tracker
                cost_tracker.record("haiku", "qa_lead", response.usage.input_tokens, response.usage.output_tokens)
                cost = cost_tracker.calculate_cost("haiku", response.usage.input_tokens, response.usage.output_tokens)

            verdict = "SHIP IT" if "SHIP IT" in response.content[0].text.upper() else "NEEDS REVIEW"
            return {"verdict": verdict, "details": response.content[0].text, "_cost": cost}

        except Exception as e:
            print(f"[TaskRunner] QA attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)

    return {"verdict": "SKIPPED", "_cost": 0}


async def resume_pending_tasks():
    """Called on server startup — resume any interrupted tasks."""
    pending = memory.get_pending_tasks()
    if not pending:
        return

    print(f"[TaskRunner] Found {len(pending)} pending tasks to resume")
    notify(f"Resuming {len(pending)} interrupted task(s)...")

    for task in pending:
        print(f"[TaskRunner] Resuming: {task['directive'][:60]}")
        asyncio.create_task(
            run_task(task["id"], task["directive"], task.get("project_path", ""), task.get("project_id", ""))
        )
