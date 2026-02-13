"""
Structured Logging with Correlation IDs — TSA Principle 16.

Provides:
- ContextVar-based correlation IDs (directive_id, task_id, thread_ts, agent_id)
- CorrelationFilter that injects IDs into every log record
- JSON formatter for file output (machine-readable)
- Human-readable formatter for console with [directive_id] prefix
- RotatingFileHandler to ~/.nexus/logs/nexus.log (10MB, 5 backups)
- set_correlation() context manager for scoped ID propagation
"""

import contextvars
import json
import logging
import logging.handlers
import os
import time
from contextlib import contextmanager

# Async-safe correlation IDs
directive_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("directive_id", default="")
task_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("task_id", default="")
thread_ts_var: contextvars.ContextVar[str] = contextvars.ContextVar("thread_ts", default="")
agent_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("agent_id", default="")


class CorrelationFilter(logging.Filter):
    """Injects correlation IDs into every log record."""

    def filter(self, record):
        record.directive_id = directive_id_var.get("")
        record.task_id = task_id_var.get("")
        record.thread_ts = thread_ts_var.get("")
        record.agent_id = agent_id_var.get("")
        return True


class JSONFormatter(logging.Formatter):
    """Machine-readable JSON log lines for file output."""

    def format(self, record):
        log_entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "directive_id": getattr(record, "directive_id", ""),
            "task_id": getattr(record, "task_id", ""),
            "thread_ts": getattr(record, "thread_ts", ""),
            "agent_id": getattr(record, "agent_id", ""),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


class CorrelationFormatter(logging.Formatter):
    """Human-readable console format with correlation ID prefix."""

    def format(self, record):
        did = getattr(record, "directive_id", "")
        tid = getattr(record, "task_id", "")
        prefix = ""
        if did:
            prefix = f"[{did}] "
        elif tid:
            prefix = f"[task:{tid}] "
        record.correlation_prefix = prefix
        return super().format(record)


@contextmanager
def set_correlation(
    directive_id: str = "",
    task_id: str = "",
    thread_ts: str = "",
    agent_id: str = "",
):
    """Context manager to set correlation IDs for the current scope."""
    tokens = []
    if directive_id:
        tokens.append(directive_id_var.set(directive_id))
    if task_id:
        tokens.append(task_id_var.set(task_id))
    if thread_ts:
        tokens.append(thread_ts_var.set(thread_ts))
    if agent_id:
        tokens.append(agent_id_var.set(agent_id))
    try:
        yield
    finally:
        for token in tokens:
            # ContextVar.reset() restores the previous value
            try:
                token.var.reset(token)
            except ValueError:
                pass


def configure_logging(log_dir: str, level: str = "INFO"):
    """Set up structured logging with file rotation and correlation IDs."""
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "nexus.log")

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on re-init
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    correlation_filter = CorrelationFilter()

    # Console handler — human-readable with correlation prefix
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.addFilter(correlation_filter)
    console_fmt = CorrelationFormatter(
        "%(asctime)s %(levelname)-7s %(correlation_prefix)s%(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)

    # File handler — JSON lines with rotation (10MB, 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.addFilter(correlation_filter)
    file_handler.setFormatter(JSONFormatter())

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "aiohttp", "slack_sdk"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
