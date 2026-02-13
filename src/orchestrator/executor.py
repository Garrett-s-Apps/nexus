"""
NEXUS Directive Executor (Lightweight)

Bypasses the heavy LangGraph orchestrator for speed.
Uses direct Sonnet API calls to plan and build.

Flow:
1. VP Engineering plans the build (Sonnet) — tech design + file list
2. Implementation agents write code (Sonnet) — one call per file
3. Quality check (Haiku) — quick lint review
4. Report back to CEO

Total: ~30-60 seconds for a small feature vs 10+ minutes through full graph.
"""

import json
import os

import anthropic

from src.config import get_key as _load_key


def _get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=_load_key("ANTHROPIC_API_KEY"))


async def execute_directive(directive: str, project_path: str, session_id: str = "") -> dict:
    """Execute a build directive end-to-end."""
    client = _get_client()
    total_cost = 0.0
    log = []

    def _log(phase: str, msg: str):
        log.append(f"[{phase}] {msg}")
        print(f"[Executor] [{phase}] {msg}")

    # Notify Slack that we're starting
    from src.slack.notifier import notify
    notify(f"Directive received: _{directive[:100]}_\nPlanning...")

    # ============================================
    # PHASE 1: VP Engineering — Technical Plan
    # ============================================
    _log("PLAN", "VP Engineering is designing the build...")

    plan_response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=f"""You are the VP of Engineering at Nexus, an autonomous software org.
The CEO has given a directive. Create a technical plan.

Project directory: {project_path}
You must output valid JSON only.

IMPORTANT: Be practical. Prefer fewer files. Use existing patterns in the project if possible.
If this is a web app, prefer a single HTML file with inline JS/CSS unless complexity demands otherwise.""",
        messages=[{"role": "user", "content": f"""Directive: {directive}

Create a build plan as JSON:
{{
    "summary": "one line description of what we're building",
    "tech_stack": "languages and frameworks",
    "files": [
        {{
            "path": "relative/path/to/file.ext",
            "purpose": "what this file does",
            "language": "python|typescript|html|etc"
        }}
    ],
    "build_order": ["file paths in order they should be created"],
    "test_strategy": "how to verify it works"
}}

Only return the JSON."""}],
    )

    plan_text = plan_response.content[0].text.strip()  # type: ignore[union-attr]
    if plan_response.usage:
        from src.cost.tracker import cost_tracker
        cost_tracker.record("sonnet", "vp_engineering", plan_response.usage.input_tokens, plan_response.usage.output_tokens)
        total_cost += cost_tracker.calculate_cost("sonnet", plan_response.usage.input_tokens, plan_response.usage.output_tokens)

    # Parse the plan
    try:
        if plan_text.startswith("```"):
            plan_text = plan_text.split("\n", 1)[1]
        if plan_text.endswith("```"):
            plan_text = plan_text.rsplit("```", 1)[0]
        plan = json.loads(plan_text.strip())
    except json.JSONDecodeError:
        _log("PLAN", "Failed to parse plan JSON, using raw text")
        return {
            "status": "error",
            "error": f"VP Engineering produced invalid plan: {plan_text[:500]}",
            "log": log,
            "cost": total_cost,
        }

    _log("PLAN", f"Plan ready: {plan.get('summary', 'N/A')}")
    _log("PLAN", f"Files to create: {len(plan.get('files', []))}")
    _log("PLAN", f"Stack: {plan.get('tech_stack', 'N/A')}")

    notify(f"Plan ready: *{plan.get('summary', directive[:60])}*\nCreating {len(plan.get('files', []))} files...")

    # ============================================
    # PHASE 2: Implementation — Write Code
    # ============================================
    _log("BUILD", "Implementation agents writing code...")

    files_created = []
    build_order = plan.get("build_order", [f["path"] for f in plan.get("files", [])])
    file_map = {f["path"]: f for f in plan.get("files", [])}

    # Context of already-written files (grows as we write)
    written_context: dict[str, str] = {}

    for file_path in build_order:
        file_info = file_map.get(file_path, {"path": file_path, "purpose": "", "language": ""})
        _log("BUILD", f"Writing {file_path}...")

        # Build context from already-written files
        context_str = ""
        if written_context:
            context_str = "\n\nAlready written files for reference:\n"
            for wp, wc in written_context.items():
                # Truncate large files in context
                content_preview = wc[:2000] if len(wc) > 2000 else wc
                context_str += f"\n--- {wp} ---\n{content_preview}\n"

        impl_response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            system=f"""You are a senior engineer at Nexus. Write production-quality code.
Project: {project_path}

RULES:
- Write COMPLETE, working code. No placeholders, no TODOs, no "implement this".
- Handle all error states.
- No hardcoded secrets.
- Include helpful comments that explain WHY, not WHAT.
- If this is a web UI, make it look professional — not a prototype.

Output ONLY the file contents. No markdown fences, no explanation, just the raw code.""",
            messages=[{"role": "user", "content": f"""Write this file:

Path: {file_path}
Purpose: {file_info.get('purpose', '')}
Language: {file_info.get('language', '')}

Overall project: {plan.get('summary', directive)}
Tech stack: {plan.get('tech_stack', '')}
{context_str}

Write the complete file contents now."""}],
        )

        file_content = impl_response.content[0].text  # type: ignore[union-attr]
        # Strip markdown fences if the model wrapped it
        if file_content.startswith("```"):
            file_content = file_content.split("\n", 1)[1]
        if file_content.rstrip().endswith("```"):
            file_content = file_content.rstrip().rsplit("```", 1)[0]

        if impl_response.usage:
            cost_tracker.record("sonnet", "implementation", impl_response.usage.input_tokens, impl_response.usage.output_tokens)
            total_cost += cost_tracker.calculate_cost("sonnet", impl_response.usage.input_tokens, impl_response.usage.output_tokens)

        # Write the file (canonicalize to block path traversal from LLM output)
        full_path = os.path.realpath(os.path.join(project_path, file_path))
        if not full_path.startswith(os.path.realpath(project_path) + os.sep):
            _log("BUILD", f"BLOCKED path traversal attempt: {file_path}")
            continue
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(file_content)

        files_created.append(file_path)
        written_context[file_path] = file_content
        _log("BUILD", f"Created {file_path} ({len(file_content)} bytes)")

    notify(f"Code written: {len(files_created)} files created.\nRunning quality check...")

    # ============================================
    # PHASE 3: Quality Check (Haiku — fast)
    # ============================================
    _log("QA", "Running quality check...")

    # Concatenate all files for review
    all_code = ""
    for fp, fc in written_context.items():
        all_code += f"\n\n=== {fp} ===\n{fc}"

    qa_response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system="You are a QA lead. Review code quickly. Focus on critical issues only: crashes, security holes, broken imports. Skip style nitpicks. Be brief.",
        messages=[{"role": "user", "content": f"""Quick review of these files:\n{all_code[:15000]}

Report:
1. Any critical bugs? (YES/NO + details)
2. Any security issues? (YES/NO + details)
3. Will this run without errors? (YES/NO + details)
4. Overall verdict: SHIP IT or NEEDS FIXES"""}],
    )

    qa_result = qa_response.content[0].text  # type: ignore[union-attr]
    if qa_response.usage:
        cost_tracker.record("haiku", "qa_lead", qa_response.usage.input_tokens, qa_response.usage.output_tokens)
        total_cost += cost_tracker.calculate_cost("haiku", qa_response.usage.input_tokens, qa_response.usage.output_tokens)

    _log("QA", "Review complete")

    ship_it = "SHIP IT" in qa_result.upper()

    # ============================================
    # PHASE 4: Git commit (if project has git)
    # ============================================
    commit_sha = None
    branch_name = None
    if os.path.exists(os.path.join(project_path, ".git")):
        try:
            from src.git_ops.git import GitOps
            git = GitOps(project_path)
            branch_name = git.create_feature_branch(directive[:30])
            git.stage_files(files_created)
            commit_sha = git.commit(f"feat: {directive[:60]}", cost=total_cost)
            _log("GIT", f"Committed {commit_sha} on {branch_name}")
        except Exception as e:
            _log("GIT", f"Git failed (non-fatal): {e}")

    # ============================================
    # PHASE 5: Report
    # ============================================
    report = f"""*Build Complete: {plan.get('summary', directive[:60])}*

Files created: {len(files_created)}
{chr(10).join(f'  • {f}' for f in files_created)}

Tech stack: {plan.get('tech_stack', 'N/A')}
QA verdict: {'Ship it' if ship_it else 'Needs review'}
Total cost: ${total_cost:.4f}"""

    if branch_name:
        report += f"\nBranch: `{branch_name}`"
    if commit_sha:
        report += f"\nCommit: `{commit_sha[:8]}`"

    notify(report)

    # Track KPI
    from src.kpi.tracker import kpi_tracker
    kpi_tracker.record_task_completion("directive_executor", directive[:100], total_cost, 0)

    return {
        "status": "complete",
        "summary": plan.get("summary", directive[:100]),
        "files_created": files_created,
        "tech_stack": plan.get("tech_stack", ""),
        "qa_result": qa_result,
        "ship_it": ship_it,
        "branch": branch_name,
        "commit": commit_sha,
        "cost": total_cost,
        "log": log,
    }
