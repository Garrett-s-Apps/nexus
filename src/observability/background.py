"""
Background Scheduler — TSA Principle 19: Separate Batch from Real-Time.

Decouples periodic maintenance tasks (ML retraining, RAG pruning, dedup cleanup)
from the real-time directive processing pipeline. Prevents CPU/GIL contention
during burst directive processing.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("nexus.background")


@dataclass
class _Job:
    name: str
    coro_fn: Callable[[], Any]
    interval_seconds: int
    run_immediately: bool = False
    last_run: float = 0.0
    run_count: int = 0
    last_error: str = ""
    enabled: bool = True


class BackgroundScheduler:
    """Manages periodic background tasks decoupled from real-time processing."""

    def __init__(self):
        self._jobs: dict[str, _Job] = {}
        self._task: asyncio.Task | None = None
        self._running = False

    def register(
        self,
        name: str,
        coro_fn,
        interval_seconds: int,
        run_immediately: bool = False,
    ):
        """Register a periodic background job."""
        self._jobs[name] = _Job(
            name=name,
            coro_fn=coro_fn,
            interval_seconds=interval_seconds,
            run_immediately=run_immediately,
        )
        logger.info("Registered background job: %s (every %ds)", name, interval_seconds)

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Background scheduler started with %d jobs", len(self._jobs))

    async def stop(self):
        """Stop all jobs gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Background scheduler stopped")

    async def _loop(self):
        """Main scheduler loop — checks jobs every 30 seconds."""
        # Run immediate jobs first
        for job in self._jobs.values():
            if job.run_immediately and job.enabled:
                await self._run_job(job)

        while self._running:
            await asyncio.sleep(30)
            now = time.time()
            for job in self._jobs.values():
                if not job.enabled:
                    continue
                elapsed = now - job.last_run
                if elapsed >= job.interval_seconds:
                    await self._run_job(job)

    async def _run_job(self, job: _Job):
        """Execute a single job with error isolation."""
        try:
            logger.debug("Running background job: %s", job.name)
            result = job.coro_fn()
            if asyncio.iscoroutine(result):
                await result
            job.run_count += 1
            job.last_run = time.time()
            job.last_error = ""
        except Exception as e:
            job.last_error = str(e)
            job.last_run = time.time()
            logger.error("Background job %s failed: %s", job.name, e)

    def status(self) -> dict:
        """Return status of all registered jobs."""
        return {
            name: {
                "enabled": job.enabled,
                "interval_seconds": job.interval_seconds,
                "run_count": job.run_count,
                "last_run": job.last_run,
                "last_error": job.last_error,
            }
            for name, job in self._jobs.items()
        }


scheduler = BackgroundScheduler()
