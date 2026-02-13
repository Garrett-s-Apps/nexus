"""
NEXUS Task Runner

Persistent, autonomous task execution. Self-contained — uses Anthropic API directly.
Tasks survive server restarts. Each step checkpointed to SQLite.
"""

import asyncio
import json
import os
import traceback

import anthropic

from src.memory.store import memory
from src.slack.notifier import notify, notify_escalation

RETRY_LIMIT = 3


from src.config import get_key as _load_key  # consolidated key loading


def _get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=_load_key("ANTHROPIC_API_KEY"))


def _track_cost(model: str, agent: str, usage) -> float:
    """Track cost and return the dollar amount."""
    if not usage:
        return 0.0
    try:
        from src.cost.tracker import cost_tracker
        cost_tracker.record(model, agent, usage.input_tokens, usage.output_tokens)
        return cost_tracker.calculate_cost(model, usage.input_tokens, usage.output_tokens)
    except Exception:
        return 0.0


async def run_task(task_id: str, directive: str, project_path: str, project_id: str = ""):
    """Execute a build task with persistent checkpointing."""
    client = _get_client()
    total_cost = 0.0

    # Ensure project directory exists
    project_path = os.path.expanduser(project_path or "~/Projects")
    os.makedirs(project_path, exist_ok=True)

    # Create or resume persistent task record
    task = memory.get_task(task_id)
    if not task:
        memory.create_task(task_id, directive, project_path, project_id)
        task = memory.get_task(task_id)

    progress = json.loads(task.get("progress", "{}") or "{}")

    def _save(**kwargs):
        nonlocal progress
        progress.update(kwargs)
        memory.update_task(task_id, progress=progress, cost=total_cost)

    try:
        memory.update_task(task_id, status="running")

        # ========== PHASE 1: PLAN ==========
        if "plan" not in progress:
            memory.update_task(task_id, current_step="planning")
            notify(f"📋 *Planning:* _{directive[:80]}_")

            plan = await _plan(client, directive, project_path)
            if not plan:
                memory.update_task(task_id, status="error", current_step="planning_failed")
                notify(f"❌ *Planning failed* for: {directive[:60]}")
                return {"status": "error", "error": "Planning failed"}

            total_cost += plan.pop("_cost", 0)
            progress["plan"] = plan
            _save(plan=plan)
            notify(f"📋 *Plan ready:* {plan.get('summary', directive[:60])}\n{len(plan.get('files', []))} files to create")
        else:
            plan = progress["plan"]

        # ========== PHASE 2: BUILD ==========
        memory.update_task(task_id, current_step="building")
        completed_files = progress.get("completed_files", [])
        written_context = progress.get("written_context", {})
        all_files = plan.get("build_order", [f["path"] for f in plan.get("files", [])])
        file_map = {f["path"]: f for f in plan.get("files", [])}

        for file_path in all_files:
            if file_path in completed_files:
                continue

            memory.update_task(task_id, current_step=f"building:{file_path}")

            file_info = file_map.get(file_path, {"path": file_path, "purpose": "", "language": ""})
            result = await _build_file(client, file_path, file_info, plan, directive, project_path, written_context)

            if result is None:
                memory.update_task(task_id, status="error", current_step=f"build_failed:{file_path}")
                notify(f"❌ *Build failed* on `{file_path}`")
                return {"status": "error", "error": f"Failed to build {file_path}"}

            total_cost += result.pop("_cost", 0)

            # Write file to disk (canonicalize to block path traversal from LLM output)
            full_path = os.path.realpath(os.path.join(project_path, file_path))
            if not full_path.startswith(os.path.realpath(project_path) + os.sep):
                print(f"[TaskRunner] BLOCKED path traversal attempt: {file_path}")
                continue
            parent_dir = os.path.dirname(full_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(result["code"])

            completed_files.append(file_path)
            written_context[file_path] = result["code"][:2000]
            _save(completed_files=completed_files, written_context=written_context)

        notify(f"✅ *Code complete:* {len(completed_files)} files written.\nRunning QA...")

        # ========== PHASE 3: QA ==========
        if "qa" not in progress:
            memory.update_task(task_id, current_step="qa")
            qa = await _qa_review(client, written_context)
            total_cost += qa.pop("_cost", 0)
            progress["qa"] = qa.get("verdict", "unknown")
            _save(qa=progress["qa"])

        # ========== PHASE 4: GIT ==========
        git_info = {}
        if "git" not in progress and os.path.exists(os.path.join(project_path, ".git")):
            memory.update_task(task_id, current_step="git")
            try:
                from src.git_ops.git import GitOps
                git = GitOps(project_path)
                branch = git.create_feature_branch(directive[:30])
                git.stage_files(completed_files)
                sha = git.commit(f"feat: {directive[:60]}", cost=total_cost)
                git_info = {"branch": branch, "commit": sha}
                _save(git=git_info)
            except Exception as e:
                print(f"[TaskRunner] Git failed (non-fatal): {e}")

        # ========== PHASE 5: COMPLETE ==========
        memory.update_task(task_id, status="complete", current_step="done")

        report = f"""✅ *Build Complete: {plan.get('summary', directive[:60])}*

*Files:* {len(completed_files)}
{chr(10).join(f'  • `{f}`' for f in completed_files)}

*Stack:* {plan.get('tech_stack', 'N/A')}
*QA:* {progress.get('qa', 'N/A')}
*Cost:* ${total_cost:.4f}"""

        if git_info.get("branch"):
            report += f"\n*Branch:* `{git_info['branch']}`"

        notify(report)

        if project_id:
            memory.update_project_status(project_id, "built", cost=total_cost)
            memory.add_project_note(project_id, f"Built: {len(completed_files)} files, ${total_cost:.4f}", "execution")

        try:
            from src.kpi.tracker import kpi_tracker
            kpi_tracker.record_task_completion("task_runner", directive[:100], total_cost, 0)
        except Exception:
            pass

        return {"status": "complete", "files": completed_files, "cost": total_cost}

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[TaskRunner] Task failed: {e}\n{tb}")
        memory.update_task(task_id, status="error", error=str(e))
        notify_escalation("task_runner", f"Task failed: {str(e)[:200]}")
        return {"status": "error", "error": str(e)}


async def _plan(client, directive, project_path, retries=RETRY_LIMIT) -> dict | None:
    for attempt in range(retries):
        try:
            resp = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=f"You are VP of Engineering. Create a build plan.\nProject dir: {project_path}\nOutput valid JSON only. Be practical — fewer files is better.",
                messages=[{"role": "user", "content": f"""Directive: {directive}

Create a build plan as JSON:
{{
    "summary": "one line description",
    "tech_stack": "languages and frameworks",
    "files": [
        {{"path": "relative/path/file.ext", "purpose": "what it does", "language": "python|typescript|html|etc"}}
    ],
    "build_order": ["file paths in creation order"],
    "test_strategy": "how to verify"
}}

Only return JSON."""}],
            )
            text = resp.content[0].text.strip()
            cost = _track_cost("sonnet", "vp_engineering", resp.usage)

            # Strip markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.rstrip().endswith("```"):
                text = text.rstrip().rsplit("```", 1)[0]

            plan = json.loads(text.strip())
            plan["_cost"] = cost
            return plan  # type: ignore[no-any-return]
        except Exception as e:
            print(f"[TaskRunner] Plan attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
    return None


async def _build_file(client, file_path, file_info, plan, directive, project_path, written_context, retries=RETRY_LIMIT) -> dict | None:
    context_str = ""
    if written_context:
        context_str = "\n\nAlready written files:\n"
        for wp, wc in list(written_context.items())[-5:]:
            context_str += f"\n--- {wp} ---\n{wc}\n"

    for attempt in range(retries):
        try:
            resp = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                system=f"Senior engineer. Write production-quality code.\nProject: {project_path}\nRULES: Complete working code. No placeholders. No TODOs. Handle errors.\nOutput ONLY file contents. No markdown fences, no explanation.",
                messages=[{"role": "user", "content": f"""Write this file:
Path: {file_path}
Purpose: {file_info.get('purpose', '')}
Language: {file_info.get('language', '')}
Project: {plan.get('summary', directive)}
Stack: {plan.get('tech_stack', '')}
{context_str}

Write the complete file now."""}],
            )
            code = resp.content[0].text
            cost = _track_cost("sonnet", "engineer", resp.usage)

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


async def _qa_review(client, written_context, retries=RETRY_LIMIT) -> dict:
    all_code = ""
    for fp, fc in written_context.items():
        all_code += f"\n=== {fp} ===\n{fc}"

    for attempt in range(retries):
        try:
            resp = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system="QA lead. Quick review for critical issues only. Be brief.",
                messages=[{"role": "user", "content": f"Review:\n{all_code[:15000]}\n\nVerdict: SHIP IT or NEEDS FIXES?"}],
            )
            cost = _track_cost("haiku", "qa_lead", resp.usage)
            verdict = "SHIP IT" if "SHIP IT" in resp.content[0].text.upper() else "NEEDS REVIEW"
            return {"verdict": verdict, "details": resp.content[0].text, "_cost": cost}
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
    notify(f"🔄 Resuming {len(pending)} interrupted task(s)...")
    for task in pending:
        print(f"[TaskRunner] Resuming: {task['directive'][:60]}")
        asyncio.create_task(
            run_task(task["id"], task["directive"], task.get("project_path", ""), task.get("project_id", ""))
        )
