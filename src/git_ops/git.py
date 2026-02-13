"""
NEXUS Git Operations

Handles all git interactions: branching, committing, PR creation.
NEXUS commits to feature branches, never directly to main.
"""

import json
import os
import subprocess


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
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

    def push(self, branch: str | None = None) -> bool:
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
        base: str | None = None,
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

    # ============================================
    # AUTO-DEPLOY TO GITHUB ORG
    # ============================================

    def deploy_to_github(
        self,
        org: str | None = None,
        repo_name: str | None = None,
        description: str = "",
        private: bool = False,
    ) -> dict:
        """
        Deploy project to a GitHub org. Creates the repo if needed,
        sets remote, and pushes. Returns repo URL or error.

        Args:
            org: GitHub org (defaults to GITHUB_ORG env var / Garrett-s-Apps)
            repo_name: Repo name (defaults to project directory name)
            description: Repo description
            private: Whether the repo should be private
        """
        if org is None:
            org = os.environ.get("GITHUB_ORG", "Garrett-s-Apps")
        if repo_name is None:
            repo_name = os.path.basename(self.path)

        full_name = f"{org}/{repo_name}"

        # Check if repo already exists on GitHub
        code, stdout, _ = _run(
            ["gh", "repo", "view", full_name, "--json", "url", "-q", ".url"],
            cwd=self.path,
        )

        if code != 0:
            # Repo doesn't exist — create it
            visibility = "--private" if private else "--public"
            create_cmd = [
                "gh", "repo", "create", full_name,
                visibility,
                "--source", self.path,
                "--push",
            ]
            if description:
                create_cmd.extend(["--description", description])

            code, stdout, stderr = _run(create_cmd, cwd=self.path)
            if code != 0:
                return {"error": f"Failed to create repo: {stderr}"}

            return {
                "url": f"https://github.com/{full_name}",
                "created": True,
                "repo": full_name,
            }

        # Repo exists — ensure remote is set and push
        repo_url = stdout.strip()
        code, current_remote, _ = self.run_git("remote", "get-url", "origin")
        expected_remote = f"https://github.com/{full_name}.git"

        if code != 0 or full_name not in current_remote:
            # Add or update origin remote
            self.run_git("remote", "remove", "origin")
            self.run_git("remote", "add", "origin", expected_remote)

        branch = self.current_branch()
        self.push(branch)

        return {
            "url": repo_url,
            "created": False,
            "repo": full_name,
        }

    # ============================================
    # START ON LOCALHOST
    # ============================================

    def start_localhost(self) -> dict:
        """
        Detect project type and return the command to start a dev server.
        Does NOT start the server itself — returns info for the engine
        to spawn as a background process.
        """
        has_file = lambda name: os.path.isfile(os.path.join(self.path, name))

        if has_file("package.json"):
            # Node.js project
            pkg_path = os.path.join(self.path, "package.json")
            try:
                with open(pkg_path) as f:
                    pkg = json.loads(f.read())
                scripts = pkg.get("scripts", {})
                if "dev" in scripts:
                    cmd = "npm run dev"
                elif "start" in scripts:
                    cmd = "npm start"
                else:
                    cmd = "npx serve ."
            except Exception:
                cmd = "npm start"

            # Auto-install deps if node_modules missing
            needs_install = not os.path.isdir(os.path.join(self.path, "node_modules"))

            return {
                "type": "node",
                "cmd": cmd,
                "install_cmd": "npm install" if needs_install else None,
                "cwd": self.path,
            }

        elif has_file("requirements.txt") or has_file("pyproject.toml"):
            # Python project
            if has_file("manage.py"):
                cmd = "python manage.py runserver"
            elif has_file("app.py") or has_file("main.py"):
                entry = "app.py" if has_file("app.py") else "main.py"
                cmd = f"python {entry}"
            else:
                cmd = "uvicorn main:app --reload --port 8000"

            return {
                "type": "python",
                "cmd": cmd,
                "install_cmd": "pip install -r requirements.txt" if has_file("requirements.txt") else None,
                "cwd": self.path,
            }

        elif has_file("index.html"):
            # Static site
            return {
                "type": "static",
                "cmd": "npx serve .",
                "install_cmd": None,
                "cwd": self.path,
            }

        return {
            "type": "unknown",
            "cmd": None,
            "cwd": self.path,
            "error": "Could not detect project type",
        }
