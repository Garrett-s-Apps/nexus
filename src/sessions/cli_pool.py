"""
CLI Session Pool — streaming Claude Code processes per Slack thread.

Each Slack thread gets its own Claude CLI process in pipe mode with
stream-json output. Events are parsed in real-time and progress
callbacks update Slack with human-readable status.

Key design decisions:
- One process per send() call (pipe mode is one-shot)
- 15-minute timeout (Opus needs time for real engineering)
- No auto-retry — errors are reported with context
- Cancellation support — follow-up messages kill the current process
- Progress streaming — tool use events surface live status to Slack
"""

import asyncio
import json
import logging
import os
import re
import shutil
import time
from collections.abc import Awaitable, Callable

from src.agents.task_result import TaskResult
from src.config import CLI_DOCKER_ENABLED, CLI_DOCKER_IMAGE, get_key

logger = logging.getLogger(__name__)

# SEC-012: Dangerous CLI patterns to block
DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/',
    r'curl.*\|\s*bash',
    r'wget.*\|\s*sh',
    r'nc\s+-[le]',
    r'eval\s*\(',
    r'exec\s*\(',
    r'__import__\s*\(',
    r'subprocess\s*\.\s*call',
    r'subprocess\s*\.\s*Popen',
    r'os\s*\.\s*system',
]

def sanitize_cli_message(message: str) -> str:
    """Validate input before sending to CLI to prevent injection attacks.

    Raises ValueError if message contains dangerous patterns or exceeds size limit.
    Also strips control characters for safety.
    """
    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            raise ValueError(f"Message contains dangerous pattern: {pattern}")

    # Check message size (50KB limit)
    if len(message) > 50000:
        raise ValueError("Message too long (max 50KB)")

    # Strip control characters except newline, carriage return, tab
    message = ''.join(c for c in message if ord(c) >= 32 or c in '\n\r\t')
    return message

CLAUDE_CMD = "claude"
DOCKER_CMD = "docker"
IDLE_TIMEOUT = 1800  # 30 minutes — session cleanup after inactivity
STALL_TIMEOUT = 900  # 15 minutes of silence = genuinely stuck (no wall-clock limit)
STREAM_BUFFER_LIMIT = 10 * 1024 * 1024  # 10 MB — stream-json lines can exceed asyncio's 64KB default

# Map CLI tool names to human-readable Slack status
_TOOL_STATUS: dict[str, str] = {
    "Read": ":book: Reading",
    "Write": ":pencil2: Writing",
    "Edit": ":pencil2: Editing",
    "Bash": ":gear: Running command",
    "Glob": ":mag: Searching files",
    "Grep": ":mag: Searching code",
    "WebFetch": ":globe_with_meridians: Fetching URL",
    "WebSearch": ":globe_with_meridians: Searching web",
    "Task": ":robot_face: Delegating to agent",
    "LSP": ":brain: Analyzing code",
    "NotebookEdit": ":pencil2: Editing notebook",
}

ProgressCallback = Callable[[str], Awaitable[None]]


class CLISession:
    """A single Claude Code CLI process with streaming and cancellation."""

    def __init__(self, thread_ts: str, project_path: str):
        self.thread_ts = thread_ts
        self.project_path = project_path
        self.process: asyncio.subprocess.Process | None = None
        self.last_used: float = time.monotonic()
        self._lock = asyncio.Lock()
        self._cancelled = False

    async def start(self) -> bool:
        use_docker = CLI_DOCKER_ENABLED and shutil.which(DOCKER_CMD)

        if not use_docker and not shutil.which(CLAUDE_CMD):
            logger.warning("Claude CLI not found, session unavailable")
            return False

        # Kill any existing process to prevent orphans
        if self.process and self.process.returncode is None:
            try:
                self.process.kill()
                await self.process.wait()
            except Exception:
                pass

        self._cancelled = False

        try:
            if use_docker:
                self.process = await self._start_docker()
            else:
                self.process = await self._start_native()

            self.last_used = time.monotonic()
            mode = "docker" if use_docker else "native"
            logger.info(
                "CLI session started (%s) for thread %s (pid=%s)",
                mode, self.thread_ts, self.process.pid,
            )
            return True
        except OSError as e:
            logger.error("Failed to start CLI session: %s", e)
            return False

    async def _start_native(self) -> asyncio.subprocess.Process:
        """Start Claude CLI as a native subprocess."""
        clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        # Inject API keys from .env.keys that may not be in os.environ
        for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
            val = get_key(key)
            if val:
                clean_env[key] = val
        return await asyncio.create_subprocess_exec(
            CLAUDE_CMD, "--model", "sonnet",
            "-p", "--verbose", "--output-format", "stream-json",
            "--dangerously-skip-permissions",
            "--append-system-prompt",
            (
                "You are a fully autonomous agent. NEVER ask the user questions or "
                "pause for confirmation. Make all decisions independently and complete "
                "the task fully without check-ins or interactive prompts. If something "
                "is unclear, make a reasonable assumption and continue. Tasks may run "
                "for hours or days — keep working until fully done."
            ),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.project_path,
            env=clean_env,
            limit=STREAM_BUFFER_LIMIT,
        )

    async def _start_docker(self) -> asyncio.subprocess.Process:
        """Start Claude CLI inside a Docker container with project mounted."""
        env_args: list[str] = []
        for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
            val = get_key(key)
            if val:
                env_args.extend(["-e", f"{key}={val}"])

        return await asyncio.create_subprocess_exec(
            DOCKER_CMD, "run", "--rm", "-i",
            "-v", f"{self.project_path}:/workspace:ro",
            "-v", f"{self.project_path}/output:/workspace/output:rw",
            *env_args,
            "-e", f"NEXUS_CLI_TIMEOUT={STALL_TIMEOUT}",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=100m",  # noqa: S108 - Docker tmpfs mount
            "--security-opt=no-new-privileges",
            "--cap-drop=ALL",
            "--memory=2g",
            "--cpus=2",
            "--pids-limit=100",
            CLI_DOCKER_IMAGE,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=STREAM_BUFFER_LIMIT,
        )

    def cancel(self):
        """Cancel the running send() — kills the process immediately."""
        self._cancelled = True
        if self.process and self.process.returncode is None:
            try:
                self.process.kill()
            except Exception:
                pass

    @property
    def is_busy(self) -> bool:
        """True if send() is currently in progress."""
        return self._lock.locked()

    async def send(
        self,
        message: str,
        timeout: int = STALL_TIMEOUT,
        on_progress: ProgressCallback | None = None,
    ) -> TaskResult:
        """Send a message and stream progress to Slack.

        Uses --output-format stream-json to parse events in real-time.
        Calls on_progress with human-readable status (never raw JSON).
        Supports cancellation via cancel().
        """
        # SEC-012: Sanitize input before sending to CLI
        try:
            message = sanitize_cli_message(message)
        except ValueError as e:
            logger.warning("CLI message rejected: %s", e)
            return TaskResult(
                status="error",
                output=f"Invalid input: {e}",
                error_type="validation_error",
            )

        async with self._lock:
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
                proc.stdin.close()

                result_text = ""
                cost_usd = 0.0
                last_progress_time = time.monotonic()
                start_time = time.monotonic()
                tool_count = 0
                tools_log: list[str] = []  # ordered list of tool names used
                files_touched: list[str] = []  # file paths read/written/edited
                raw_lines: list[str] = []
                last_output_time = time.monotonic()

                while True:
                    # Check cancellation
                    if self._cancelled:
                        logger.info("CLI cancelled for thread %s", self.thread_ts)
                        if proc.returncode is None:
                            proc.kill()
                            await proc.wait()
                        return TaskResult(
                            status="error",
                            output="Redirected by follow-up message",
                            error_type="cancelled",
                        )

                    # No wall-clock limit — only kill if truly stalled (no output for stall_timeout)
                    silent_secs = time.monotonic() - last_output_time
                    if silent_secs >= timeout:
                        logger.warning(
                            "CLI stalled (no output for %ds) for thread %s",
                            timeout, self.thread_ts,
                        )
                        proc.kill()
                        await proc.wait()
                        partial = result_text.strip() or "(no output before stall)"
                        return TaskResult(
                            status="timeout",
                            output=f"CLI stalled — no output for {timeout // 60} minutes "
                            f"({tool_count} tools used). Task may have hung.\n\n"
                            f"Partial output:\n{partial[:2000]}",
                            error_type="timeout",
                        )

                    # Read next line with 30s sub-timeout for heartbeats
                    try:
                        line = await asyncio.wait_for(
                            proc.stdout.readline(),
                            timeout=30,
                        )
                        # Any output resets the stall clock
                        last_output_time = time.monotonic()
                    except TimeoutError:
                        # No output for 30s — send heartbeat (not a timeout, just silence)
                        if on_progress and (time.monotonic() - last_progress_time) > 25:
                            heartbeat_secs = int(time.monotonic() - self.last_used)
                            mins, secs = divmod(heartbeat_secs, 60)
                            time_str = f"{mins}m{secs}s" if mins else f"{secs}s"
                            await on_progress(
                                f":hourglass_flowing_sand: Still working... "
                                f"({time_str}, {tool_count} tools used)"
                            )
                            last_progress_time = time.monotonic()
                        continue

                    if not line:
                        break  # EOF — process finished

                    line_str = line.decode(errors="replace").strip()
                    if not line_str:
                        continue

                    raw_lines.append(line_str)

                    # Try to parse as stream-json event
                    try:
                        event = json.loads(line_str)
                    except json.JSONDecodeError:
                        # Raw text output (non-JSON fallback)
                        result_text += line_str + "\n"
                        continue

                    event_type = event.get("type", "")

                    if event_type == "result":
                        result_text = event.get("result", result_text)
                        cost_usd = event.get("cost_usd", 0.0) or 0.0
                        subtype = event.get("subtype", "")
                        if subtype == "error":
                            error_msg = event.get("error", "Unknown error")
                            return TaskResult(
                                status="error",
                                output=f"CLI error: {error_msg}",
                                error_type="cli_error",
                                error_detail=error_msg,
                                cost_usd=cost_usd,
                            )

                    elif event_type == "assistant":
                        msg = event.get("message", {})
                        content_blocks = msg.get("content", [])
                        for block in content_blocks:
                            if not isinstance(block, dict):
                                continue
                            block_type = block.get("type", "")

                            if block_type == "tool_use":
                                tool_name = block.get("name", "")
                                tool_count += 1
                                tools_log.append(tool_name)
                                status = _TOOL_STATUS.get(
                                    tool_name, f":wrench: {tool_name}"
                                )

                                # Add context for specific tools
                                tool_input = block.get("input", {})
                                if tool_name in ("Read", "Write", "Edit"):
                                    fp = tool_input.get("file_path", "")
                                    if fp:
                                        status += f" `{fp.split('/')[-1]}`"
                                        if fp not in files_touched:
                                            files_touched.append(fp)
                                elif tool_name == "Bash":
                                    cmd = tool_input.get("command", "")
                                    if cmd:
                                        status += f": `{cmd[:50]}`"

                                logger.info(
                                    "CLI [%d] %s for thread %s",
                                    tool_count, status, self.thread_ts,
                                )

                                # Rate-limit progress updates (every 5s)
                                now = time.monotonic()
                                if on_progress and (now - last_progress_time) > 5:
                                    await on_progress(status)
                                    last_progress_time = now

                            elif block_type == "text":
                                # Intermediate text — don't accumulate,
                                # result event has the final version
                                pass

                # Process exited — collect stderr
                await proc.wait()
                stderr_data = b""
                if proc.stderr:
                    stderr_data = await proc.stderr.read()
                stderr_text = stderr_data.decode(errors="replace").strip()

                if not result_text and stderr_text:
                    logger.warning(
                        "CLI stderr for thread %s: %s",
                        self.thread_ts, stderr_text[:500],
                    )
                    return TaskResult(
                        status="error",
                        output=f"CLI error: {stderr_text[:500]}",
                        error_type="api_error",
                        error_detail=stderr_text[:500],
                    )

                # If no result event was parsed, try raw lines
                if not result_text and raw_lines:
                    result_text = "\n".join(raw_lines)

                elapsed: float = time.monotonic() - start_time
                return TaskResult(
                    status="success",
                    output=result_text.strip() or "(No response from CLI)",
                    cost_usd=cost_usd,
                    elapsed_seconds=round(elapsed, 1),
                    metadata={
                        "tools_used": tool_count,
                        "tools_log": tools_log,
                        "files_touched": files_touched,
                    },
                )

            except Exception as e:
                logger.error(
                    "CLI session error for thread %s: %s", self.thread_ts, e,
                )
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
    """Manages multiple concurrent CLI sessions per Slack thread.

    A thread is a directive scope. Multiple CLI processes can run in parallel
    within the same thread — e.g. "build the API" + "also add dark mode".
    Queries (cost, status, org) bypass CLI entirely via Haiku intake.
    """

    def __init__(self):
        self._sessions: dict[str, list[CLISession]] = {}
        self._cleanup_task: asyncio.Task | None = None

    def spawn(self, thread_ts: str, project_path: str) -> CLISession:
        """Create a new CLI session for this thread (always creates fresh)."""
        session = CLISession(thread_ts, project_path)
        if thread_ts not in self._sessions:
            self._sessions[thread_ts] = []
        self._sessions[thread_ts].append(session)
        return session

    def has_busy_sessions(self, thread_ts: str) -> bool:
        """True if any CLI session in this thread is currently executing."""
        return any(s.is_busy for s in self._sessions.get(thread_ts, []))

    def busy_count(self, thread_ts: str) -> int:
        """Number of actively executing sessions in this thread."""
        return sum(1 for s in self._sessions.get(thread_ts, []) if s.is_busy)

    async def cancel_all(self, thread_ts: str) -> int:
        """Cancel all active sessions in a thread. Returns count cancelled."""
        cancelled = 0
        for session in self._sessions.get(thread_ts, []):
            if session.is_busy:
                session.cancel()
                cancelled += 1
        return cancelled

    async def cleanup_stale(self):
        stale_threads: list[str] = []
        for ts, sessions in self._sessions.items():
            # Remove idle sessions from the list
            active = [s for s in sessions if not s.is_idle]
            idle = [s for s in sessions if s.is_idle]
            for s in idle:
                await s.kill()
            if active:
                self._sessions[ts] = active
            else:
                stale_threads.append(ts)
        for ts in stale_threads:
            del self._sessions[ts]
        if stale_threads:
            logger.info("Cleaned up %d stale thread session groups", len(stale_threads))

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
        for sessions in self._sessions.values():
            for session in sessions:
                await session.kill()
        self._sessions.clear()

    def active_count(self) -> int:
        return sum(
            1
            for sessions in self._sessions.values()
            for s in sessions
            if s.alive
        )

    def status(self) -> dict:
        all_sessions = []
        for ts, sessions in self._sessions.items():
            for i, s in enumerate(sessions):
                all_sessions.append({
                    "thread_ts": ts,
                    "session_index": i,
                    "alive": s.alive,
                    "busy": s.is_busy,
                    "idle_seconds": round(time.monotonic() - s.last_used, 1),
                })
        return {
            "active_sessions": self.active_count(),
            "total_threads": len(self._sessions),
            "sessions": all_sessions,
        }


# Global pool
cli_pool = CLISessionPool()
