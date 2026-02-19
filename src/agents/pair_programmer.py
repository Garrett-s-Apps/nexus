"""
Pair Programmer Agent

An SDK-invocable agent that takes a codebase path + natural-language instruction,
loads context files (AGENT.md, SKILL.md, CLAUDE.md), and produces targeted code
changes routed through the NEXUS engineering org.

Usage:
    from src.agents.pair_programmer import PairProgrammerAgent

    agent = PairProgrammerAgent()
    result = await agent.run(
        cwd="/path/to/project",
        instruction="Refactor the auth module to use refresh tokens",
        files=["src/auth/login.py"],     # optional: pre-attach files
        rules=["security-rules"],        # optional: pre-load rule files
    )
    print(result.diff)
    print(result.summary)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.cost.tracker import CostTracker


@dataclass
class PairProgrammerResult:
    """Structured result from a pair-programming session."""

    instruction: str
    summary: str
    diff: str
    files_modified: list[str]
    agent_trace: list[dict[str, str]]
    cost_usd: float
    raw_response: str


@dataclass
class PairProgrammerAgent:
    """
    SDK agent for AI-assisted pair programming.

    Routes instructions through the NEXUS Chief of Staff to the appropriate
    engineering agents. Automatically loads project context from AGENT.md,
    SKILL.md, and CLAUDE.md before sending the instruction.
    """

    # Agent identity used in cost tracking and org routing
    agent_id: str = "pair_programmer"
    model: str = "sonnet"

    # Context file names to search for, in priority order
    _context_filenames: list[str] = field(
        default_factory=lambda: ["AGENT.md", "SKILL.md", "CLAUDE.md"],
        init=False,
        repr=False,
    )

    async def run(
        self,
        cwd: str,
        instruction: str,
        files: list[str] | None = None,
        rules: list[str] | None = None,
    ) -> PairProgrammerResult:
        """
        Execute a pair-programming instruction against a codebase.

        Args:
            cwd: Absolute path to the project root.
            instruction: Natural-language description of the change to make.
            files: Optional list of file paths to attach as context.
            rules: Optional list of rule file names to load (resolved relative to cwd).

        Returns:
            PairProgrammerResult with diff, summary, and agent trace.
        """
        # Late import avoids circular dependency with orchestrator
        from src.orchestrator.executor import execute_directive  # type: ignore[import]

        context = self._load_context(cwd, files or [], rules or [])
        user_message = self._build_user_message(instruction, context)

        agent_trace: list[dict[str, str]] = []

        # execute_directive routes through the full NEXUS agent pipeline
        result_dict = await execute_directive(
            directive=user_message,
            project_path=cwd,
            session_id=f"99-{self.agent_id}",
        )

        raw_response: str = result_dict.get("response", result_dict.get("summary", str(result_dict)))
        cost_usd: float = float(result_dict.get("cost_usd", 0.0))

        # Collect agent activity from the result log if present
        for entry in result_dict.get("log", []):
            agent_trace.append({"agent": "nexus", "message": str(entry)})

        # Record cost against the pair_programmer agent bucket
        cost_tracker = CostTracker()
        cost_tracker.record(
            model=self.model,
            agent_name=self.agent_id,
            tokens_in=result_dict.get("tokens_in", 0),
            tokens_out=result_dict.get("tokens_out", 0),
            project="pair_programmer",
        )

        diff, summary, modified = self._parse_response(raw_response)

        return PairProgrammerResult(
            instruction=instruction,
            summary=summary,
            diff=diff,
            files_modified=modified,
            agent_trace=agent_trace,
            cost_usd=cost_usd,
            raw_response=raw_response,
        )

    # ------------------------------------------------------------------
    # Context loading
    # ------------------------------------------------------------------

    def _load_context(
        self,
        cwd: str,
        files: list[str],
        rules: list[str],
    ) -> dict[str, Any]:
        """
        Walk up from cwd to find and load context files.
        Also loads any explicitly attached files and rule files.
        """
        context_docs: dict[str, str] = {}

        # Search upward from cwd for each context filename
        for filename in self._context_filenames:
            content = self._find_file_upward(cwd, filename)
            if content:
                context_docs[filename] = content

        # Load explicitly attached files
        attached: dict[str, str] = {}
        for filepath in files:
            full = filepath if os.path.isabs(filepath) else os.path.join(cwd, filepath)
            if os.path.isfile(full):
                try:
                    attached[filepath] = Path(full).read_text(encoding="utf-8")
                except OSError:
                    pass  # Non-readable file — skip silently

        # Load rule files (look for <name>.md and <name>.txt in cwd)
        loaded_rules: dict[str, str] = {}
        for rule in rules:
            for ext in (".md", ".txt", ""):
                rule_path = os.path.join(cwd, f"{rule}{ext}")
                if os.path.isfile(rule_path):
                    try:
                        loaded_rules[rule] = Path(rule_path).read_text(encoding="utf-8")
                    except OSError:
                        pass
                    break

        return {
            "cwd": cwd,
            "context_docs": context_docs,
            "attached_files": attached,
            "rules": loaded_rules,
        }

    def _find_file_upward(self, start_dir: str, filename: str) -> str | None:
        """Walk up the directory tree from start_dir looking for filename."""
        current = Path(start_dir).resolve()
        # Stop at filesystem root or after 10 levels to avoid runaway traversal
        for _ in range(10):
            candidate = current / filename
            if candidate.is_file():
                try:
                    return candidate.read_text(encoding="utf-8")
                except OSError:
                    return None
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_system_prompt(self, context: dict[str, Any]) -> str:
        parts = [
            "You are a pair-programming agent in the NEXUS multi-agent engineering org.",
            "Your job is to analyze the codebase, understand the instruction, and produce",
            "precise, targeted code changes. Route complex work to the appropriate NEXUS",
            "engineering agents. Return a structured response with a diff and summary.",
            "",
            "Rules:",
            "- Never use type: any in TypeScript.",
            "- Never hardcode secrets or API keys.",
            "- Comments explain WHY, never WHAT.",
            "- All changes must pass ruff (Python) or eslint (TypeScript).",
            "- Changes go to branch nexus/self-update, never main.",
        ]

        # Inject loaded context docs
        for name, content in context.get("context_docs", {}).items():
            parts += ["", f"=== {name} ===", content]

        # Inject loaded rule files
        for name, content in context.get("rules", {}).items():
            parts += ["", f"=== Rule: {name} ===", content]

        return "\n".join(parts)

    def _build_user_message(self, instruction: str, context: dict[str, Any]) -> str:
        parts = [f"[99] {instruction}", ""]

        attached = context.get("attached_files", {})
        if attached:
            parts.append("Attached files for context:")
            for filepath, content in attached.items():
                parts += [f"\n--- {filepath} ---", content]

        parts += [
            "",
            "Produce a unified diff of all changes, a one-sentence summary of what",
            "was changed, and a list of modified file paths.",
        ]

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, raw: str) -> tuple[str, str, list[str]]:
        """
        Extract diff, summary, and modified files from the agent response.

        The agent is instructed to return these sections. This is a best-effort
        parse — if sections are missing, we return the raw response as the diff.
        """
        diff = ""
        summary = ""
        modified: list[str] = []

        lines = raw.splitlines()

        in_diff = False
        diff_lines: list[str] = []
        summary_lines: list[str] = []
        modified_lines: list[str] = []
        section = "none"

        for line in lines:
            lower = line.strip().lower()

            if lower.startswith("```diff") or lower.startswith("--- ") and not in_diff:
                in_diff = True
                section = "diff"
                continue
            if in_diff and lower.startswith("```"):
                in_diff = False
                continue
            if lower.startswith("summary:") or lower == "## summary":
                section = "summary"
                # Grab inline content after "Summary:"
                after = line.split(":", 1)[-1].strip() if ":" in line else ""
                if after:
                    summary_lines.append(after)
                continue
            if lower.startswith("modified files:") or lower == "## modified files":
                section = "modified"
                continue

            if section == "diff" or in_diff:
                diff_lines.append(line)
            elif section == "summary":
                if line.strip():
                    summary_lines.append(line.strip())
            elif section == "modified":
                stripped = line.strip().lstrip("-").lstrip("*").strip()
                if stripped:
                    modified_lines.append(stripped)

        diff = "\n".join(diff_lines) if diff_lines else raw
        summary = " ".join(summary_lines) if summary_lines else raw[:200]
        modified = modified_lines if modified_lines else []

        return diff, summary, modified
