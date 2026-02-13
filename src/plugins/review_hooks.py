"""
Post-completion plugin review hooks.

After agents finish work, this module orchestrates three parallel plugin-based
reviews via Claude Code CLI sessions:
  1. LSP Diagnostics Review — type errors, anti-patterns via ast_grep
  2. Security Review — secrets, injection patterns, auth validation
  3. Code Quality Review — dead code, style, API usage via Context7

Each review spawns a CLI session with sonnet and returns structured
ReviewResult with findings, severity, and pass/fail.
"""

import asyncio
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("nexus.plugins.review_hooks")

REVIEW_TIMEOUT = 300  # 5 minutes per review


@dataclass
class ReviewFinding:
    file: str
    line: int | None
    severity: str  # critical, high, medium, low, info
    category: str
    message: str


@dataclass
class ReviewResult:
    review_type: str
    passed: bool
    findings: list[ReviewFinding] = field(default_factory=list)
    error: str | None = None
    elapsed_seconds: float = 0.0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity in ("critical", "high"))


def detect_project_languages(project_path: str) -> list[str]:
    """Detect programming languages in use based on file extensions."""
    langs = set()
    ext_map = {
        ".py": "python", ".ts": "typescript", ".tsx": "tsx",
        ".js": "javascript", ".jsx": "javascript", ".go": "go",
        ".rs": "rust", ".java": "java", ".rb": "ruby",
        ".css": "css", ".html": "html",
    }
    src_path = os.path.join(project_path, "src")
    scan_path = src_path if os.path.isdir(src_path) else project_path

    for root, _dirs, files in os.walk(scan_path):
        # Skip vendored/generated directories
        if any(skip in root for skip in ("node_modules", "venv", ".venv", ".git", "__pycache__")):
            continue
        for f in files:
            ext = os.path.splitext(f)[1]
            if ext in ext_map:
                langs.add(ext_map[ext])
        if len(langs) >= 5:
            break
    return sorted(langs) if langs else ["python"]


async def _run_cli_review(prompt: str, project_path: str) -> str:
    """Spawn a Claude Code CLI session for a review task."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return json.dumps({"error": "Claude CLI not found"})

    cmd = [
        claude_bin,
        "--dangerously-skip-permissions",
        "--model", "claude-sonnet-4-5-20250929",
        "--output-format", "text",
        "-p", prompt,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(), timeout=REVIEW_TIMEOUT
        )
        return stdout.decode("utf-8", errors="replace").strip()
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return json.dumps({"error": f"Review timed out after {REVIEW_TIMEOUT}s"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _parse_findings(raw: str, review_type: str) -> ReviewResult:
    """Parse CLI output into structured ReviewResult."""
    start = time.time()
    findings = []

    # Try to extract JSON findings from the output
    try:
        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                items = json.loads(line)
                for item in items:
                    findings.append(ReviewFinding(
                        file=item.get("file", "unknown"),
                        line=item.get("line"),
                        severity=item.get("severity", "info"),
                        category=item.get("category", review_type),
                        message=item.get("message", ""),
                    ))
                break
    except (json.JSONDecodeError, TypeError):
        pass

    # If no structured findings, check for error indicators in raw text
    if not findings and raw:
        error_keywords = ["error", "critical", "vulnerability", "injection", "hardcoded"]
        has_issues = any(kw in raw.lower() for kw in error_keywords)
        if has_issues:
            findings.append(ReviewFinding(
                file="review_output",
                line=None,
                severity="info",
                category=review_type,
                message=raw[:500],
            ))

    critical = sum(1 for f in findings if f.severity in ("critical", "high"))
    return ReviewResult(
        review_type=review_type,
        passed=critical == 0,
        findings=findings,
        elapsed_seconds=time.time() - start,
    )


async def run_lsp_review(changed_files: list[str], project_path: str) -> ReviewResult:
    """Run LSP diagnostics and AST pattern checks on changed files."""
    start = time.time()
    langs = detect_project_languages(project_path)
    files_str = "\n".join(f"- {f}" for f in changed_files[:20])

    prompt = (
        "You are a code diagnostics reviewer. Analyze these changed files for errors.\n\n"
        f"Changed files:\n{files_str}\n\n"
        "Steps:\n"
        "1. Run `lsp_diagnostics_directory` on the project directory to find type errors and warnings.\n"
        f"2. For each language ({', '.join(langs)}), use `ast_grep_search` to find anti-patterns:\n"
        "   - Python: bare `except:`, mutable default args, wildcard imports\n"
        "   - TypeScript: `any` type usage, ts-ignore without justification\n"
        "   - General: debug logging left in production code, TODO/FIXME comments\n"
        "3. Report findings as a JSON array on a single line:\n"
        '[{"file":"path","line":10,"severity":"high","category":"lsp","message":"description"}]\n\n'
        "If no issues found, output: []"
    )

    raw = await _run_cli_review(prompt, project_path)
    result = _parse_findings(raw, "lsp_diagnostics")
    result.elapsed_seconds = time.time() - start
    return result


async def run_security_review(changed_files: list[str], project_path: str) -> ReviewResult:
    """Run security-focused review on changed files."""
    start = time.time()
    files_str = "\n".join(f"- {f}" for f in changed_files[:20])

    prompt = (
        "You are a security reviewer. Scan these changed files for vulnerabilities.\n\n"
        f"Changed files:\n{files_str}\n\n"
        "Steps:\n"
        "1. Use `ast_grep_search` to find OWASP Top 10 injection patterns:\n"
        "   - SQL injection via string formatting or concatenation\n"
        "   - Command injection via shell=True or os.system calls\n"
        "   - XSS via innerHTML assignment or unsafe HTML rendering\n"
        "2. Use `Grep` to search for hardcoded secrets: API keys, passwords, tokens in source files.\n"
        "3. Use `lsp_find_references` on auth/session/token functions to verify trust boundaries.\n"
        "4. Report findings as a JSON array on a single line:\n"
        '[{"file":"path","line":10,"severity":"critical","category":"security","message":"description"}]\n\n'
        "If no issues found, output: []"
    )

    raw = await _run_cli_review(prompt, project_path)
    result = _parse_findings(raw, "security")
    result.elapsed_seconds = time.time() - start
    return result


async def run_quality_review(changed_files: list[str], project_path: str) -> ReviewResult:
    """Run code quality review on changed files."""
    start = time.time()
    files_str = "\n".join(f"- {f}" for f in changed_files[:20])

    prompt = (
        "You are a code quality reviewer. Check these changed files for quality issues.\n\n"
        f"Changed files:\n{files_str}\n\n"
        "Steps:\n"
        "1. Use `lsp_diagnostics` on each changed file to verify zero warnings.\n"
        "2. Use `ast_grep_search` to find dead code patterns: unreachable code after return, unused imports.\n"
        "3. Use `lsp_document_symbols` to check that function/class naming is consistent.\n"
        "4. Use Context7 MCP tools to verify any library API usage is correct (if applicable).\n"
        "5. Report findings as a JSON array on a single line:\n"
        '[{"file":"path","line":10,"severity":"medium","category":"quality","message":"description"}]\n\n'
        "If no issues found, output: []"
    )

    raw = await _run_cli_review(prompt, project_path)
    result = _parse_findings(raw, "quality")
    result.elapsed_seconds = time.time() - start
    return result


async def run_plugin_review_suite(
    changed_files: list[str],
    project_path: str,
) -> dict[str, Any]:
    """
    Run all three plugin reviews in parallel.

    Returns a summary dict with results, overall pass/fail, and any critical findings.
    Non-blocking on failure — if a review errors out, it's logged but doesn't block.
    """
    if not changed_files:
        return {"passed": True, "results": [], "critical_findings": 0}

    project_path = project_path or os.environ.get(
        "NEXUS_PROJECT_PATH", os.path.expanduser("~/Projects/nexus")
    )

    results = await asyncio.gather(
        run_lsp_review(changed_files, project_path),
        run_security_review(changed_files, project_path),
        run_quality_review(changed_files, project_path),
        return_exceptions=True,
    )

    parsed_results: list[ReviewResult] = []
    total_critical = 0

    for r in results:
        if isinstance(r, BaseException):
            logger.error(f"Plugin review failed: {r}")
            parsed_results.append(ReviewResult(
                review_type="unknown", passed=True, error=str(r),
            ))
        elif isinstance(r, ReviewResult):
            parsed_results.append(r)
            total_critical += r.critical_count

    return {
        "passed": total_critical == 0,
        "results": parsed_results,
        "critical_findings": total_critical,
    }
