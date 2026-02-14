"""
NEXUS Checkpoint Manager

Auto-saves project state at intervals and on demand.
Enables recovery from crashes or context loss.
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path.home() / ".nexus" / "checkpoints"
MAX_CHECKPOINTS = 10


@dataclass
class GitState:
    """Git repository state snapshot."""
    branch: str | None = None
    commit: str | None = None
    uncommitted_changes: int = 0
    has_stash: bool = False
    error: str | None = None


@dataclass
class MemoryState:
    """Memory database state snapshot."""
    session_count: int = 0
    active_sessions: int = 0
    last_modified: str | None = None


@dataclass
class TaskBoardState:
    """Task board state snapshot."""
    total_tasks: int = 0
    completed: int = 0
    in_progress: int = 0
    failed: int = 0


@dataclass
class CostState:
    """Cost tracking snapshot."""
    total_cost_usd: float = 0.0
    hourly_rate: float = 0.0
    by_model: dict[str, float] = field(default_factory=dict)
    by_agent: dict[str, float] = field(default_factory=dict)


@dataclass
class Checkpoint:
    """Complete checkpoint state."""
    timestamp: str
    name: str
    manual: bool
    git: GitState
    memory: MemoryState
    tasks: TaskBoardState
    cost: CostState
    project_path: str | None = None


class CheckpointManager:
    """Manages checkpoint creation, listing, and restoration."""

    def __init__(self, project_path: str | None = None):
        """Initialize checkpoint manager.

        Args:
            project_path: Project directory path for git operations
        """
        self.project_path = project_path or os.getcwd()
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    def _get_timestamp(self) -> str:
        """Get ISO timestamp for checkpoint naming."""
        return datetime.now().isoformat().replace(":", "-").replace(".", "-")

    def _get_git_state(self) -> GitState:
        """Capture current git repository state."""
        try:
            branch = subprocess.check_output(
                ["git", "branch", "--show-current"],
                cwd=self.project_path,
                encoding="utf8",
                stderr=subprocess.DEVNULL
            ).strip()

            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_path,
                encoding="utf8",
                stderr=subprocess.DEVNULL
            ).strip()

            status = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                encoding="utf8",
                stderr=subprocess.DEVNULL
            )
            uncommitted = len([line for line in status.split("\n") if line.strip()])

            stash_list = subprocess.check_output(
                ["git", "stash", "list"],
                cwd=self.project_path,
                encoding="utf8",
                stderr=subprocess.DEVNULL
            )
            has_stash = bool(stash_list.strip())

            return GitState(
                branch=branch,
                commit=commit,
                uncommitted_changes=uncommitted,
                has_stash=has_stash
            )
        except subprocess.CalledProcessError:
            return GitState(error="Not a git repository")
        except Exception as e:
            return GitState(error=str(e))

    def _get_memory_state(self) -> MemoryState:
        """Capture memory database state."""
        memory_db_path = Path.home() / ".nexus" / "memory.db"
        if not memory_db_path.exists():
            return MemoryState()

        try:
            import sqlite3
            conn = sqlite3.connect(str(memory_db_path))
            cursor = conn.cursor()

            # Get session counts
            cursor.execute("SELECT COUNT(*) FROM sessions")
            session_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'active'")
            active_sessions = cursor.fetchone()[0]

            # Get last modified time
            last_modified = datetime.fromtimestamp(
                memory_db_path.stat().st_mtime
            ).isoformat()

            conn.close()

            return MemoryState(
                session_count=session_count,
                active_sessions=active_sessions,
                last_modified=last_modified
            )
        except Exception as e:
            logger.warning("Failed to read memory state: %s", e)
            return MemoryState()

    def _get_task_state(self) -> TaskBoardState:
        """Capture task board state from NexusState if available."""
        # This would integrate with actual state tracking
        # For now, return empty state
        return TaskBoardState()

    def _get_cost_state(self) -> CostState:
        """Capture current cost tracking state."""
        try:
            from src.agents.sdk_bridge import cost_tracker

            return CostState(
                total_cost_usd=cost_tracker.total_cost,
                hourly_rate=cost_tracker.hourly_rate,
                by_model=dict(cost_tracker.by_model),
                by_agent=dict(cost_tracker.by_agent)
            )
        except Exception as e:
            logger.warning("Failed to read cost state: %s", e)
            return CostState()

    def save_checkpoint(self, name: str | None = None, manual: bool = False) -> str:
        """Save a checkpoint of current state.

        Args:
            name: Optional checkpoint name (auto-generated if not provided)
            manual: Whether this is a manual checkpoint

        Returns:
            Checkpoint name
        """
        timestamp = self._get_timestamp()
        checkpoint_name = name or f"checkpoint-{timestamp}"
        checkpoint_path = CHECKPOINT_DIR / f"{checkpoint_name}.json"

        # Gather state
        checkpoint = Checkpoint(
            timestamp=datetime.now().isoformat(),
            name=checkpoint_name,
            manual=manual,
            git=self._get_git_state(),
            memory=self._get_memory_state(),
            tasks=self._get_task_state(),
            cost=self._get_cost_state(),
            project_path=self.project_path
        )

        # Convert to dict for JSON serialization
        checkpoint_dict = {
            "timestamp": checkpoint.timestamp,
            "name": checkpoint.name,
            "manual": checkpoint.manual,
            "git": {
                "branch": checkpoint.git.branch,
                "commit": checkpoint.git.commit,
                "uncommitted_changes": checkpoint.git.uncommitted_changes,
                "has_stash": checkpoint.git.has_stash,
                "error": checkpoint.git.error
            },
            "memory": {
                "session_count": checkpoint.memory.session_count,
                "active_sessions": checkpoint.memory.active_sessions,
                "last_modified": checkpoint.memory.last_modified
            },
            "tasks": {
                "total_tasks": checkpoint.tasks.total_tasks,
                "completed": checkpoint.tasks.completed,
                "in_progress": checkpoint.tasks.in_progress,
                "failed": checkpoint.tasks.failed
            },
            "cost": {
                "total_cost_usd": checkpoint.cost.total_cost_usd,
                "hourly_rate": checkpoint.cost.hourly_rate,
                "by_model": checkpoint.cost.by_model,
                "by_agent": checkpoint.cost.by_agent
            },
            "project_path": checkpoint.project_path
        }

        # Save checkpoint
        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint_dict, f, indent=2)

        # Cleanup old checkpoints
        self._cleanup_old_checkpoints()

        logger.info("Checkpoint saved: %s", checkpoint_name)
        return checkpoint_name

    def _cleanup_old_checkpoints(self) -> None:
        """Remove old auto-saved checkpoints, keeping only MAX_CHECKPOINTS."""
        # Get all auto-saved checkpoints (non-manual)
        checkpoints = []
        for file_path in CHECKPOINT_DIR.glob("checkpoint-*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)
                    if not data.get("manual", False):
                        checkpoints.append((file_path, file_path.stat().st_mtime))
            except Exception:
                continue

        # Sort by modification time (newest first)
        checkpoints.sort(key=lambda x: x[1], reverse=True)

        # Delete old checkpoints
        for file_path, _ in checkpoints[MAX_CHECKPOINTS:]:
            try:
                file_path.unlink()
                logger.debug("Deleted old checkpoint: %s", file_path.name)
            except Exception as e:
                logger.warning("Failed to delete checkpoint %s: %s", file_path, e)

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """List all available checkpoints.

        Returns:
            List of checkpoint metadata dicts
        """
        checkpoints = []
        for file_path in sorted(CHECKPOINT_DIR.glob("*.json"), reverse=True):
            try:
                with open(file_path) as f:
                    data = json.load(f)
                    checkpoints.append({
                        "name": data["name"],
                        "timestamp": data["timestamp"],
                        "manual": data.get("manual", False),
                        "branch": data.get("git", {}).get("branch"),
                        "uncommitted": data.get("git", {}).get("uncommitted_changes", 0),
                        "cost": data.get("cost", {}).get("total_cost_usd", 0.0)
                    })
            except Exception as e:
                logger.warning("Failed to read checkpoint %s: %s", file_path, e)
                continue

        return checkpoints

    def restore_checkpoint(self, checkpoint_name: str) -> bool:
        """Display restore instructions for a checkpoint.

        Does not automatically restore state - shows commands user should run.

        Args:
            checkpoint_name: Name of checkpoint to restore

        Returns:
            True if checkpoint exists and instructions displayed
        """
        checkpoint_path = CHECKPOINT_DIR / f"{checkpoint_name}.json"

        if not checkpoint_path.exists():
            logger.error("Checkpoint not found: %s", checkpoint_name)
            return False

        try:
            with open(checkpoint_path) as f:
                data = json.load(f)

            print("\n" + "=" * 63)
            print(f"🔄 RESTORING CHECKPOINT: {checkpoint_name}")
            print("=" * 63 + "\n")

            print("Checkpoint State:")
            print(f"  Timestamp: {data['timestamp']}")

            git_state = data.get("git", {})
            print(f"  Branch: {git_state.get('branch')}")
            print(f"  Commit: {git_state.get('commit', '')[:8]}")
            print(f"  Modified Files: {git_state.get('uncommitted_changes', 0)}")

            memory_state = data.get("memory", {})
            if memory_state.get("session_count", 0) > 0:
                print("\nMemory State:")
                print(f"  Total Sessions: {memory_state.get('session_count')}")
                print(f"  Active Sessions: {memory_state.get('active_sessions')}")

            tasks_state = data.get("tasks", {})
            if tasks_state.get("total_tasks", 0) > 0:
                print("\nTask State:")
                print(f"  Total: {tasks_state.get('total_tasks')}")
                print(f"  Completed: {tasks_state.get('completed')}")
                print(f"  In Progress: {tasks_state.get('in_progress')}")
                print(f"  Failed: {tasks_state.get('failed')}")

            cost_state = data.get("cost", {})
            print("\nCost State:")
            print(f"  Total: ${cost_state.get('total_cost_usd', 0.0):.2f}")
            print(f"  Hourly Rate: ${cost_state.get('hourly_rate', 0.0):.2f}/hr")

            print("\nTo restore git state:")
            if git_state.get("branch"):
                print(f"  git checkout {git_state['branch']}")
            if git_state.get("commit"):
                print(f"  git reset --hard {git_state['commit']}")

            print("\n⚠️  Manual restoration required. Review the state above.")
            print("=" * 63 + "\n")

            return True

        except Exception as e:
            logger.error("Failed to read checkpoint: %s", e)
            return False


def auto_checkpoint_wrapper(func):
    """Decorator to auto-checkpoint before executing a function.

    Usage:
        @auto_checkpoint_wrapper
        async def my_node(state: NexusState) -> dict:
            ...
    """
    async def wrapper(state, *args, **kwargs):
        # Create checkpoint before node execution
        checkpoint_manager = CheckpointManager(state.project_path)
        checkpoint_name = f"before-{func.__name__}-{state.current_phase}"
        checkpoint_manager.save_checkpoint(checkpoint_name, manual=False)

        # Execute the actual node function
        return await func(state, *args, **kwargs)

    return wrapper
