"""
NEXUS Codebase Analyzer Agent (MAINT-011)

Analyzes codebases for security, performance, architecture, code quality,
UX, data integrity, maintainability, and compliance issues.

Produces structured findings that can be executed as rebuild tasks.
"""

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agents.base import Agent, allm_call
from src.agents.org_chart import SONNET

logger = logging.getLogger("nexus.analyzer")


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------
CATEGORIES = ("SEC", "PERF", "ARCH", "CODE", "UX", "DATA", "MAINT", "COMP")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
EFFORTS = ("XS", "S", "M", "L", "XL")


@dataclass
class Finding:
    """A single analysis finding."""

    id: str  # e.g. "SEC-001"
    category: str  # one of CATEGORIES
    severity: str  # one of SEVERITIES
    title: str
    description: str
    location: str  # e.g. "src/server.py:42"
    impact: str
    remediation: str
    effort: str  # one of EFFORTS
    effort_hours: str  # e.g. "2-8 hours"
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | in-progress | completed
    risk: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Analysis state persistence
# ---------------------------------------------------------------------------
def save_analysis_state(findings: list[Finding], target_dir: str, project_name: str = "") -> str:
    """Save analysis results to .claude/analysis-state.json."""
    if not project_name:
        project_name = os.path.basename(os.path.abspath(target_dir))

    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_category[f.category] = by_category.get(f.category, 0) + 1

    # Estimate total effort hours from effort_hours strings
    total_hours = _estimate_total_hours(findings)

    state = {
        "projectName": project_name,
        "version": "1.0",
        "analyzedAt": datetime.now(UTC).isoformat(),
        "targetDirectory": os.path.abspath(target_dir),
        "summary": {
            "totalFindings": len(findings),
            "bySeverity": by_severity,
            "byCategory": by_category,
            "totalEffortHours": total_hours,
            "estimatedWorkDays": round(total_hours / 8, 1),
        },
        "findings": [f.to_dict() for f in findings],
    }

    state_dir = os.path.join(target_dir, ".claude")
    os.makedirs(state_dir, exist_ok=True)
    state_path = os.path.join(state_dir, "analysis-state.json")

    with open(state_path, "w") as fp:
        json.dump(state, fp, indent=2)

    logger.info("Analysis state saved to %s (%d findings)", state_path, len(findings))
    return state_path


def load_analysis_state(target_dir: str) -> dict[str, Any] | None:
    """Load analysis state from .claude/analysis-state.json."""
    state_path = os.path.join(target_dir, ".claude", "analysis-state.json")
    if not os.path.exists(state_path):
        return None
    with open(state_path) as fp:
        result: dict[str, Any] = json.load(fp)
        return result


def _estimate_total_hours(findings: list[Finding]) -> int:
    """Estimate total hours from effort_hours strings like '2-8 hours' or '1-3 days'."""
    total = 0.0
    for f in findings:
        text = f.effort_hours.lower()
        numbers = re.findall(r"(\d+)", text)
        if not numbers:
            continue
        nums = [int(n) for n in numbers]
        avg = sum(nums) / len(nums)
        if "day" in text:
            avg *= 8
        total += avg
    return round(total)


# ---------------------------------------------------------------------------
# AnalyzerAgent
# ---------------------------------------------------------------------------
class AnalyzerAgent(Agent):
    """Analyzes codebases for security, performance, architecture, and code quality issues.

    Scans a target directory and produces structured findings across categories:
    SEC, PERF, ARCH, CODE, UX, DATA, MAINT, COMP.
    """

    async def do_work(self, decision, directive_id):
        """Standard agent work loop -- analyze the project."""
        from src.memory.store import memory

        directive = memory.get_directive(directive_id)
        if not directive:
            return "No directive"

        target_dir = directive.get("project_path", "") or os.path.expanduser("~/Projects/nexus-output")
        result = await self.analyze_codebase(target_dir)
        return json.dumps(result["summary"], indent=2)

    async def analyze_codebase(
        self,
        target_dir: str,
        focus_areas: list[str] | None = None,
    ) -> dict:
        """Analyze a codebase and return structured findings.

        Args:
            target_dir: Path to the codebase to analyze.
            focus_areas: Optional list of categories to focus on (e.g. ["SEC", "PERF"]).
                         If None, all categories are analyzed.

        Returns:
            {"findings": list[Finding], "summary": dict, "state_path": str}
        """
        if not os.path.isdir(target_dir):
            raise ValueError(f"Target directory does not exist: {target_dir}")

        categories = focus_areas or list(CATEGORIES)
        # Validate categories
        categories = [c.upper() for c in categories if c.upper() in CATEGORIES]
        if not categories:
            categories = list(CATEGORIES)

        # Collect file inventory for the LLM
        file_inventory = self._collect_file_inventory(target_dir)

        # Collect code samples from key files
        code_samples = self._collect_code_samples(target_dir, file_inventory)

        # Run analysis via LLM
        findings = await self._run_analysis(target_dir, categories, file_inventory, code_samples)

        # Save state
        state_path = save_analysis_state(findings, target_dir)

        summary: dict[str, Any] = {
            "totalFindings": len(findings),
            "bySeverity": {},
            "byCategory": {},
        }
        for f in findings:
            by_sev: dict[str, int] = summary["bySeverity"]
            by_cat: dict[str, int] = summary["byCategory"]
            by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
            by_cat[f.category] = by_cat.get(f.category, 0) + 1

        return {
            "findings": findings,
            "summary": summary,
            "state_path": state_path,
        }

    def _collect_file_inventory(self, target_dir: str, max_files: int = 200) -> list[str]:
        """Walk the target directory and collect file paths (relative)."""
        skip_dirs = {
            ".git", "node_modules", "__pycache__", ".venv", "venv",
            ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
            ".tox", "egg-info", ".eggs",
        }
        files: list[str] = []
        for root, dirs, filenames in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for fname in filenames:
                if fname.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(root, fname), target_dir)
                files.append(rel)
                if len(files) >= max_files:
                    return files
        return files

    def _collect_code_samples(
        self,
        target_dir: str,
        file_inventory: list[str],
        max_total_chars: int = 30000,
    ) -> str:
        """Read key source files and return concatenated samples."""
        # Prioritize: config, main entry, agents, security, tests
        priority_patterns = [
            r"(config|settings)\.(py|ts|js|yaml|yml|json)$",
            r"main\.(py|ts|js)$",
            r"(server|app)\.(py|ts|js)$",
            r"agent", r"security", r"auth",
            r"test_", r"_test\.", r"\.test\.",
            r"requirements\.txt$", r"package\.json$", r"pyproject\.toml$",
        ]

        scored: list[tuple[int, str]] = []
        for f in file_inventory:
            score = 0
            for i, pat in enumerate(priority_patterns):
                if re.search(pat, f, re.IGNORECASE):
                    score = len(priority_patterns) - i
                    break
            scored.append((score, f))

        scored.sort(key=lambda x: -x[0])

        samples = []
        total = 0
        for _score, fpath in scored:
            if total >= max_total_chars:
                break
            full = os.path.join(target_dir, fpath)
            try:
                with open(full, errors="replace") as fp:
                    content = fp.read(5000)
                samples.append(f"--- {fpath} ---\n{content}")
                total += len(content)
            except (OSError, UnicodeDecodeError):
                continue

        return "\n\n".join(samples)

    async def _run_analysis(
        self,
        target_dir: str,
        categories: list[str],
        file_inventory: list[str],
        code_samples: str,
    ) -> list[Finding]:
        """Run LLM-powered analysis and parse findings."""
        project_name = os.path.basename(os.path.abspath(target_dir))
        cats_desc = ", ".join(categories)

        prompt = f"""You are a senior codebase analyst. Analyze this codebase and produce findings.

PROJECT: {project_name}
DIRECTORY: {target_dir}
CATEGORIES TO ANALYZE: {cats_desc}

Category definitions:
- SEC: Security vulnerabilities (injection, auth bypass, secrets exposure, XSS)
- PERF: Performance bottlenecks (N+1 queries, missing indexes, memory leaks)
- ARCH: Architecture issues (tight coupling, missing abstractions, circular deps)
- CODE: Code quality (dead code, duplication, poor naming, missing types)
- UX: User experience issues (confusing flows, missing feedback, accessibility)
- DATA: Data integrity (race conditions, missing validation, schema issues)
- MAINT: Maintainability (missing docs, no tests, complex functions)
- COMP: Compliance (license issues, GDPR, logging PII)

FILE INVENTORY ({len(file_inventory)} files):
{chr(10).join(file_inventory[:100])}

CODE SAMPLES:
{code_samples[:25000]}

Produce findings as a JSON array. Each finding must have:
- id: "<CATEGORY>-<3-digit-number>" e.g. "SEC-001"
- category: one of {cats_desc}
- severity: "CRITICAL", "HIGH", "MEDIUM", or "LOW"
- title: concise title
- description: detailed description of the issue
- location: "file.py:line" or "file.py" or "multiple files"
- impact: what happens if this is not fixed
- remediation: specific steps to fix
- effort: "XS" (< 1hr), "S" (1-4hr), "M" (4-16hr), "L" (2-5 days), "XL" (5+ days)
- effort_hours: human-readable estimate e.g. "2-8 hours"
- dependencies: list of other finding IDs this depends on (empty list if none)
- risk: brief risk statement

Be thorough but practical. Focus on HIGH and CRITICAL issues first.
Aim for 10-20 findings across the requested categories.

Output ONLY a JSON array of findings. No markdown, no explanation."""

        try:
            response, cost = await allm_call(prompt, SONNET, max_tokens=8192)
            self._total_cost += cost
        except Exception as e:
            logger.error("Analysis LLM call failed: %s", e)
            return []

        return self._parse_findings(response)

    def _parse_findings(self, raw: str) -> list[Finding]:
        """Parse LLM output into Finding objects."""
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        # Find JSON array
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start < 0 or end <= start:
            logger.error("No JSON array found in analysis output")
            return []

        try:
            items = json.loads(cleaned[start:end])
        except json.JSONDecodeError as e:
            logger.error("Failed to parse analysis JSON: %s", e)
            return []

        findings: list[Finding] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                # Normalize fields
                item.setdefault("dependencies", [])
                item.setdefault("status", "pending")
                item.setdefault("risk", "")
                item.setdefault("effort_hours", "unknown")
                item.setdefault("effort", "M")
                item.setdefault("impact", "")
                item.setdefault("remediation", "")
                item.setdefault("location", "unknown")

                findings.append(Finding.from_dict(item))
            except (TypeError, KeyError) as e:
                logger.warning("Skipping malformed finding: %s", e)
                continue

        logger.info("Parsed %d findings from analysis", len(findings))
        return findings


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------
def get_findings_by_severity(target_dir: str, severity: str) -> list[dict]:
    """Get all findings of a given severity from saved state."""
    state = load_analysis_state(target_dir)
    if not state:
        return []
    return [f for f in state["findings"] if f["severity"].upper() == severity.upper()]


def get_findings_by_category(target_dir: str, category: str) -> list[dict]:
    """Get all findings of a given category from saved state."""
    state = load_analysis_state(target_dir)
    if not state:
        return []
    return [f for f in state["findings"] if f["category"].upper() == category.upper()]


def get_finding_by_id(target_dir: str, finding_id: str) -> dict | None:
    """Get a single finding by ID from saved state."""
    state = load_analysis_state(target_dir)
    if not state:
        return None
    for f in state["findings"]:
        if f["id"].upper() == finding_id.upper():
            return f  # type: ignore[no-any-return]
    return None


def update_finding_status(target_dir: str, finding_id: str, status: str) -> bool:
    """Update the status of a finding in the saved state."""
    state_path = os.path.join(target_dir, ".claude", "analysis-state.json")
    if not os.path.exists(state_path):
        return False

    with open(state_path) as fp:
        state = json.load(fp)

    for f in state["findings"]:
        if f["id"].upper() == finding_id.upper():
            f["status"] = status
            with open(state_path, "w") as fp:
                json.dump(state, fp, indent=2)
            return True
    return False
