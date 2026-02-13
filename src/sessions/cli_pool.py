"""
CLI Session Pool — persistent Claude Code processes per Slack thread.

Each Slack thread gets its own long-lived `claude` CLI process.
Messages in the same thread are piped to the same process, preserving
conversational context without re-sending history.

Idle sessions are cleaned up after a configurable timeout.
"""

import asyncio
import logging
import os
import shutil
import time

from src.agents.task_result import TaskResult

logger = logging.getLogger(__name__)

CLAUDE_CMD = "claude"
IDLE_TIMEOUT = 1800  # 30 minutes


class CLISession:
    """A single persistent Claude Code CLI process."""

    def __init__(self, thread_ts: str, project_path: str):
        self.thread_ts = thread_ts
        self.project_path = project_path
        self.process: asyncio.subprocess.Process | None = None
        self.last_used: float = time.monotonic()
        self._lock = asyncio.Lock()

    async def start(self) -> bool:
        if not shutil.which(CLAUDE_CMD):
            logger.warning("Claude CLI not found, session unavailable")
            return False

        try:
            # Strip CLAUDECODE env var so spawned CLI avoids nested-session block
            clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            # Uses create_subprocess_exec (not shell) — args passed as array, safe from injection
            self.process = await asyncio.create_subprocess_exec(
                CLAUDE_CMD, "--dangerously-skip-permissions", "--model", "opus", "-p",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_path,
                env=clean_env,
            )
            self.last_used = time.monotonic()
            logger.info("CLI session started for thread %s (pid=%s)", self.thread_ts, self.process.pid)
            return True
        except OSError as e:
            logger.error("Failed to start CLI session: %s", e)
            return False

    async def send(self, message: str, timeout: int = 300) -> TaskResult:
        """Send a message to the CLI process and collect the response.

        The CLI runs in pipe mode (-p), which reads stdin until EOF then responds.
        Each send() spawns a fresh process, writes the message, closes stdin to
        signal EOF, then waits for the process to finish and collects all output.
        """
        async with self._lock:
            # Always start a fresh process — pipe mode is one-shot
            if not await self.start():
                return TaskResult(
                    status="unavailable", output="CLI session unavailable",
                    error_type="cli_not_found",
                )

            self.last_used = time.monotonic()

            try:
                proc = self.process
                if not proc or not proc.stdin or not proc.stdout:
                    return TaskResult(
                        status="unavailable", output="CLI session unavailable",
                        error_type="cli_not_found",
                    )

                proc.stdin.write(message.encode())
                await proc.stdin.drain()
                proc.stdin.close()  # Signal EOF so -p mode starts processing

                # Wait for the process to finish and collect all output.
                # communicate() reads stdout/stderr until EOF and waits for
                # process exit — no premature truncation from buffer polling.
                try:
                    stdout_data, stderr_data = await asyncio.wait_for(
                        proc.communicate(), timeout=timeout,
                    )
                except TimeoutError:
                    logger.warning("CLI timed out after %ds for thread %s", timeout, self.thread_ts)
                    proc.kill()
                    await proc.wait()
                    return TaskResult(
                        status="timeout",
                        output="(CLI timed out — the request may be too complex)",
                        error_type="timeout",
                    )

                result = stdout_data.decode(errors="replace").strip() if stdout_data else ""
                stderr_text = stderr_data.decode(errors="replace").strip() if stderr_data else ""

                if not result and stderr_text:
                    logger.warning("CLI stderr for thread %s: %s", self.thread_ts, stderr_text[:500])
                    return TaskResult(
                        status="error", output=f"CLI error: {stderr_text[:300]}",
                        error_type="api_error", error_detail=stderr_text[:500],
                    )

                return TaskResult(
                    status="success", output=result or "(No response from CLI)",
                )

            except Exception as e:
                logger.error("CLI session error for thread %s: %s", self.thread_ts, e)
                return TaskResult(
                    status="error", output=f"CLI error: {e}",
                    error_type="api_error", error_detail=str(e),
                )

    @property
    def is_idle(self) -> bool:
        return (time.monotonic() - self.last_used) > IDLE_TIMEOUT

    @property
    def alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def kill(self):
        if self.process and self.process.returncode is None:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except TimeoutError:
                self.process.kill()
            logger.info("CLI session killed for thread %s", self.thread_ts)


class CLISessionPool:
    """Manages persistent Claude Code CLI sessions per Slack thread."""

    def __init__(self):
        self._sessions: dict[str, CLISession] = {}
        self._cleanup_task: asyncio.Task | None = None

    async def get_or_create(self, thread_ts: str, project_path: str) -> CLISession:
        if thread_ts in self._sessions and self._sessions[thread_ts].alive:
            session = self._sessions[thread_ts]
            session.last_used = time.monotonic()
            return session

        session = CLISession(thread_ts, project_path)
        if await session.start():
            self._sessions[thread_ts] = session
        return session

    async def send_message(self, thread_ts: str, message: str, project_path: str) -> TaskResult:
        session = await self.get_or_create(thread_ts, project_path)
        return await session.send(message)

    async def cleanup_stale(self):
        stale = [ts for ts, s in self._sessions.items() if s.is_idle]
        for ts in stale:
            await self._sessions[ts].kill()
            del self._sessions[ts]
        if stale:
            logger.info("Cleaned up %d stale CLI sessions", len(stale))

    def start_cleanup_loop(self):
        if self._cleanup_task is not None:
            return

        async def _loop():
            while True:
                await asyncio.sleep(300)
                await self.cleanup_stale()

        self._cleanup_task = asyncio.ensure_future(_loop())

    async def shutdown(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
        for session in self._sessions.values():
            await session.kill()
        self._sessions.clear()

    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.alive)

    def status(self) -> dict:
        return {
            "active_sessions": self.active_count(),
            "total_created": len(self._sessions),
            "sessions": [
                {
                    "thread_ts": ts,
                    "alive": s.alive,
                    "idle_seconds": round(time.monotonic() - s.last_used, 1),
                }
                for ts, s in self._sessions.items()
            ],
        }


# Global pool
cli_pool = CLISessionPool()
