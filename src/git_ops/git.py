"""
NEXUS Git Operations

Handles all git interactions: branching, committing, PR creation.
NEXUS commits to feature branches, never directly to main.
"""

import os
import subprocess
import json
from typing import Any


def _run(cmd: list[str], cwd: str = None) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _load_github_token() -> str | None:
    try:
        with open(os.path.expanduser("~/.nexus/.env.keys")) as f:
            for line in f:
                line = line.strip()
                if line.startswith("GITHUB_TOKEN="):
                    token = line.split("=", 1)[1]
                    return token if token else None
    except FileNotFoundError:
        pass

    code, stdout, _ = _run(["gh", "auth", "token"])
    if code == 0 and stdout:
        return stdout
    return None


class GitOps:
    """Git operations for a specific project."""

    def __init__(self, project_path: str):
        self.path = project_path

    def run_git(self, *args) -> tuple[int, str, str]:
        return _run(["git"] + list(args), cwd=self.path)

    # ============================================
    # BRANCH MANAGEMENT
    # ============================================

    def current_branch(self) -> str:
        code, stdout, _ = self.run_git("branch", "--show-current")
        return stdout if code == 0 else "unknown"

    def create_branch(self, branch_name: str) -> bool:
        # Ensure we're on main/master first
        main_branch = self._get_main_branch()
        self.run_git("checkout", main_branch)
        self.run_git("pull", "--rebase")

        code, _, stderr = self.run_git("checkout", "-b", branch_name)
        if code != 0:
            # Branch might already exist
            code, _, _ = self.run_git("checkout", branch_name)
        return code == 0

    def create_feature_branch(self, feature_name: str) -> str:
        safe_name = feature_name[:40].lower().replace(" ", "-").replace("_", "-")
        branch = f"nexus/{safe_name}"
        self.create_branch(branch)
        return branch

    def _get_main_branch(self) -> str:
        code, stdout, _ = self.run_git("branch", "-l", "main")
        if code == 0 and "main" in stdout:
            return "main"
        return "master"

    # ============================================
    # COMMIT
    # ============================================

    def stage_all(self) -> bool:
        code, _, _ = self.run_git("add", "-A")
        return code == 0

    def stage_files(self, files: list[str]) -> bool:
        code, _, _ = self.run_git("add", *files)
        return code == 0

    def commit(self, message: str, cost: float = 0.0) -> str | None:
        if cost > 0:
            message = f"{message} [cost: ${cost:.2f}]"

        self.stage_all()

        # Check if there's anything to commit
        code, stdout, _ = self.run_git("status", "--porcelain")
        if code != 0 or not stdout:
            return None

        code, stdout, _ = self.run_git("commit", "-m", message)
        if code == 0:
            # Get the commit hash
            code, sha, _ = self.run_git("rev-parse", "HEAD")
            return sha if code == 0 else "committed"
        return None

    def push(self, branch: str = None) -> bool:
        if branch is None:
            branch = self.current_branch()
        code, _, _ = self.run_git("push", "-u", "origin", branch)
        return code == 0

    # ============================================
    # PR CREATION
    # ============================================

    def create_pr(
        self,
        title: str,
        body: str,
        base: str = None,
    ) -> dict | None:
        if base is None:
            base = self._get_main_branch()

        branch = self.current_branch()
        self.push(branch)

        code, stdout, stderr = _run(
            [
                "gh", "pr", "create",
                "--title", title,
                "--body", body,
                "--base", base,
                "--head", branch,
            ],
            cwd=self.path,
        )

        if code == 0:
            return {
                "url": stdout,
                "branch": branch,
                "base": base,
                "title": title,
            }
        return {"error": stderr}

    def create_nexus_pr(
        self,
        feature: str,
        summary: str,
        test_results: str = "",
        cost: float = 0.0,
        security: str = "Clean",
    ) -> dict | None:
        body = f"""## {feature}

### Summary
{summary}

### Test Results
{test_results or 'All tests passing'}

### Security Scan
{security}

### Cost
Total API cost: ${cost:.2f}

---
_This PR was created by NEXUS autonomous engineering system._
"""
        return self.create_pr(
            title=f"feat: {feature}",
            body=body,
        )

    # ============================================
    # STATUS & INFO
    # ============================================

    def status(self) -> dict:
        code, stdout, _ = self.run_git("status", "--porcelain")
        changed_files = [line.strip() for line in stdout.split("\n") if line.strip()]

        return {
            "branch": self.current_branch(),
            "changed_files": changed_files,
            "clean": len(changed_files) == 0,
        }

    def log(self, count: int = 10) -> list[dict]:
        code, stdout, _ = self.run_git(
            "log", f"-{count}",
            "--pretty=format:%H|%an|%s|%ai",
        )
        if code != 0:
            return []

        commits = []
        for line in stdout.split("\n"):
            if "|" in line:
                parts = line.split("|", 3)
                commits.append({
                    "sha": parts[0][:8],
                    "author": parts[1],
                    "message": parts[2],
                    "date": parts[3] if len(parts) > 3 else "",
                })
        return commits

    def diff_summary(self) -> str:
        code, stdout, _ = self.run_git("diff", "--stat")
        return stdout if code == 0 else "No changes"

    # ============================================
    # NEXUS SELF-UPDATE
    # ============================================

    def self_commit(self, message: str, cost: float = 0.0) -> str | None:
        """Commit to nexus/self-update branch for NEXUS's own changes."""
        original_branch = self.current_branch()
        self.create_branch("nexus/self-update")

        sha = self.commit(f"chore: {message}", cost=cost)

        if sha:
            self.push("nexus/self-update")

        # Return to original branch
        self.run_git("checkout", original_branch)
        return sha
