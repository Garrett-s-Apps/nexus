"""
NEXUS Memory System

Persistent memory that survives restarts. Three layers:

1. Conversation History — full message log, auto-summarized for context windows
2. Project Memory — decisions, plans, status for each project
3. Personal Context — things about Garrett that persist forever

Storage: SQLite at ~/.nexus/memory.db
"""

import os
import json
import time
import sqlite3
import asyncio
from datetime import datetime, timedelta
from typing import Any


DB_PATH = os.path.expanduser("~/.nexus/memory.db")


class Memory:
    def __init__(self):
        self.db_path = DB_PATH
        self._conn = None

    def init(self):
        """Initialize the database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        c = self._conn.cursor()

        # Full conversation messages
        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT DEFAULT 'slack',
                category TEXT DEFAULT '',
                cost REAL DEFAULT 0
            )
        """)

        # Conversation summaries (compressed history)
        c.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                summary TEXT NOT NULL,
                message_count INTEGER DEFAULT 0
            )
        """)

        # Project memory
        c.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                path TEXT,
                status TEXT DEFAULT 'discussing',
                tech_stack TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                total_cost REAL DEFAULT 0
            )
        """)

        # Project discussion notes / decisions
        c.execute("""
            CREATE TABLE IF NOT EXISTS project_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                note_type TEXT DEFAULT 'discussion',
                content TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)

        # Personal context — things about Garrett
        c.execute("""
            CREATE TABLE IF NOT EXISTS context (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Task queue — persistent tasks that survive restarts
        c.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                directive TEXT NOT NULL,
                project_path TEXT,
                status TEXT DEFAULT 'queued',
                current_step TEXT DEFAULT '',
                progress TEXT DEFAULT '{}',
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                cost REAL DEFAULT 0,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)

        self._conn.commit()

    # ============================================
    # CONVERSATION MESSAGES
    # ============================================

    def add_message(self, role: str, content: str, source: str = "slack", category: str = "", cost: float = 0):
        """Store a message."""
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO messages (timestamp, role, content, source, category, cost) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), role, content, source, category, cost),
        )
        self._conn.commit()

    def get_recent_messages(self, limit: int = 50) -> list[dict]:
        """Get the most recent messages."""
        c = self._conn.cursor()
        c.execute(
            "SELECT role, content, timestamp FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in c.fetchall()]
        rows.reverse()  # Oldest first
        return rows

    def get_messages_since(self, hours: int = 24) -> list[dict]:
        """Get messages from the last N hours."""
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        c = self._conn.cursor()
        c.execute(
            "SELECT role, content, timestamp FROM messages WHERE timestamp > ? ORDER BY id",
            (since,),
        )
        return [dict(r) for r in c.fetchall()]

    def get_message_count(self) -> int:
        c = self._conn.cursor()
        c.execute("SELECT COUNT(*) FROM messages")
        return c.fetchone()[0]

    # ============================================
    # CONVERSATION SUMMARIES
    # ============================================

    def add_summary(self, summary: str, period_start: str, period_end: str, message_count: int):
        """Store a conversation summary."""
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO summaries (timestamp, period_start, period_end, summary, message_count) VALUES (?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), period_start, period_end, summary, message_count),
        )
        self._conn.commit()

    def get_recent_summaries(self, limit: int = 10) -> list[dict]:
        """Get the most recent conversation summaries."""
        c = self._conn.cursor()
        c.execute(
            "SELECT summary, period_start, period_end, message_count FROM summaries ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in c.fetchall()]
        rows.reverse()
        return rows

    def get_unsummarized_count(self) -> int:
        """How many messages haven't been summarized yet."""
        c = self._conn.cursor()
        c.execute("SELECT MAX(period_end) FROM summaries")
        row = c.fetchone()
        last_summarized = row[0] if row[0] else "1970-01-01"
        c.execute("SELECT COUNT(*) FROM messages WHERE timestamp > ?", (last_summarized,))
        return c.fetchone()[0]

    # ============================================
    # PROJECTS
    # ============================================

    def create_project(self, project_id: str, name: str, description: str = "", path: str = "", tech_stack: str = ""):
        """Create or update a project."""
        now = datetime.utcnow().isoformat()
        c = self._conn.cursor()
        c.execute("""
            INSERT INTO projects (id, name, description, path, tech_stack, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, description=excluded.description,
                path=excluded.path, tech_stack=excluded.tech_stack, updated_at=excluded.updated_at
        """, (project_id, name, description, path, tech_stack, now, now))
        self._conn.commit()

    def get_project(self, project_id: str) -> dict | None:
        c = self._conn.cursor()
        c.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_active_projects(self) -> list[dict]:
        c = self._conn.cursor()
        c.execute("SELECT * FROM projects WHERE status != 'archived' ORDER BY updated_at DESC")
        return [dict(r) for r in c.fetchall()]

    def update_project_status(self, project_id: str, status: str, cost: float = 0):
        c = self._conn.cursor()
        c.execute(
            "UPDATE projects SET status = ?, total_cost = total_cost + ?, updated_at = ? WHERE id = ?",
            (status, cost, datetime.utcnow().isoformat(), project_id),
        )
        self._conn.commit()

    def add_project_note(self, project_id: str, content: str, note_type: str = "discussion"):
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO project_notes (project_id, timestamp, note_type, content) VALUES (?, ?, ?, ?)",
            (project_id, datetime.utcnow().isoformat(), note_type, content),
        )
        self._conn.commit()

    def get_project_notes(self, project_id: str, limit: int = 20) -> list[dict]:
        c = self._conn.cursor()
        c.execute(
            "SELECT * FROM project_notes WHERE project_id = ? ORDER BY id DESC LIMIT ?",
            (project_id, limit),
        )
        rows = [dict(r) for r in c.fetchall()]
        rows.reverse()
        return rows

    def search_projects(self, query: str) -> list[dict]:
        """Fuzzy search projects by name or description."""
        c = self._conn.cursor()
        c.execute(
            "SELECT * FROM projects WHERE name LIKE ? OR description LIKE ? ORDER BY updated_at DESC",
            (f"%{query}%", f"%{query}%"),
        )
        return [dict(r) for r in c.fetchall()]

    # ============================================
    # PERSONAL CONTEXT
    # ============================================

    def set_context(self, key: str, value: str):
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO context (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def get_context(self, key: str) -> str | None:
        c = self._conn.cursor()
        c.execute("SELECT value FROM context WHERE key = ?", (key,))
        row = c.fetchone()
        return row[0] if row else None

    def get_all_context(self) -> dict[str, str]:
        c = self._conn.cursor()
        c.execute("SELECT key, value FROM context")
        return {r["key"]: r["value"] for r in c.fetchall()}

    # ============================================
    # TASKS
    # ============================================

    def create_task(self, task_id: str, directive: str, project_path: str = "", project_id: str = "") -> dict:
        now = datetime.utcnow().isoformat()
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO tasks (id, project_id, directive, project_path, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', ?, ?)",
            (task_id, project_id, directive, project_path, now, now),
        )
        self._conn.commit()
        return {"id": task_id, "status": "queued"}

    def update_task(self, task_id: str, status: str = None, current_step: str = None,
                    progress: dict = None, error: str = None, cost: float = None):
        c = self._conn.cursor()
        updates = ["updated_at = ?"]
        values = [datetime.utcnow().isoformat()]

        if status:
            updates.append("status = ?")
            values.append(status)
            if status == "complete":
                updates.append("completed_at = ?")
                values.append(datetime.utcnow().isoformat())
        if current_step:
            updates.append("current_step = ?")
            values.append(current_step)
        if progress:
            updates.append("progress = ?")
            values.append(json.dumps(progress))
        if error:
            updates.append("error = ?")
            values.append(error)
        if cost is not None:
            updates.append("cost = ?")
            values.append(cost)

        values.append(task_id)
        c.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
        self._conn.commit()

    def get_task(self, task_id: str) -> dict | None:
        c = self._conn.cursor()
        c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_pending_tasks(self) -> list[dict]:
        """Get tasks that are queued or running (for resume on restart)."""
        c = self._conn.cursor()
        c.execute("SELECT * FROM tasks WHERE status IN ('queued', 'running', 'retrying') ORDER BY created_at")
        return [dict(r) for r in c.fetchall()]

    def get_recent_tasks(self, limit: int = 10) -> list[dict]:
        c = self._conn.cursor()
        c.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in c.fetchall()]

    # ============================================
    # CONTEXT BUILDING (for API calls)
    # ============================================

    def build_context_window(self, max_tokens: int = 4000) -> str:
        """
        Build a context string for the conversation engine.
        Combines: summaries + recent messages + active projects + personal context.
        Stays within approximate token budget.
        """
        parts = []

        # Personal context (always included, small)
        ctx = self.get_all_context()
        if ctx:
            parts.append("ABOUT GARRETT:")
            for k, v in ctx.items():
                parts.append(f"  {k}: {v}")

        # Active projects
        projects = self.get_active_projects()
        if projects:
            parts.append("\nACTIVE PROJECTS:")
            for p in projects[:10]:
                parts.append(f"  • {p['name']} ({p['status']}): {p['description'][:100]}")
                notes = self.get_project_notes(p["id"], limit=3)
                for n in notes:
                    parts.append(f"    - [{n['note_type']}] {n['content'][:150]}")

        # Recent summaries
        summaries = self.get_recent_summaries(5)
        if summaries:
            parts.append("\nRECENT CONVERSATION SUMMARIES:")
            for s in summaries:
                parts.append(f"  [{s['period_start'][:10]} to {s['period_end'][:10]}] {s['summary'][:300]}")

        # Pending tasks
        tasks = self.get_pending_tasks()
        if tasks:
            parts.append("\nPENDING/RUNNING TASKS:")
            for t in tasks:
                parts.append(f"  • {t['directive'][:80]} — status: {t['status']}, step: {t['current_step']}")

        context = "\n".join(parts)

        # Rough token estimate (4 chars per token)
        if len(context) > max_tokens * 4:
            context = context[:max_tokens * 4]

        return context

    def build_message_history(self, max_messages: int = 30) -> list[dict]:
        """
        Build API-ready message history.
        Uses recent messages, prepending summaries as a system-style context.
        """
        messages = self.get_recent_messages(max_messages)
        return [{"role": m["role"], "content": m["content"]} for m in messages]


# Singleton
memory = Memory()
