"""
NEXUS Session Persistence

SQLite-backed session storage. Conversations survive server restarts.
Each session tracks: directive, state snapshots, messages, cost.
"""

import json
import os
import time

import aiosqlite

DB_PATH = os.path.expanduser("~/.nexus/sessions.db")


class SessionStore:
    """Async SQLite session store."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._initialized = False

    async def init(self):
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    directive TEXT NOT NULL,
                    source TEXT DEFAULT 'slack',
                    project_path TEXT DEFAULT '',
                    status TEXT DEFAULT 'created',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    completed_at REAL,
                    total_cost REAL DEFAULT 0.0,
                    error TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS session_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    agent TEXT,
                    content TEXT NOT NULL,
                    cost REAL DEFAULT 0.0,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS session_state (
                    session_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON session_messages(session_id)
            """)
            await db.commit()
        self._initialized = True

    async def create_session(
        self,
        session_id: str,
        directive: str,
        source: str = "slack",
        project_path: str = "",
    ) -> dict:
        await self.init()
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO sessions (id, directive, source, project_path, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'running', ?, ?)""",
                (session_id, directive, source, project_path, now, now),
            )
            await db.commit()
        return {
            "id": session_id,
            "directive": directive,
            "source": source,
            "status": "running",
            "created_at": now,
        }

    async def update_status(self, session_id: str, status: str, error: str | None = None):
        await self.init()
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            if status == "complete":
                await db.execute(
                    "UPDATE sessions SET status = ?, updated_at = ?, completed_at = ?, error = ? WHERE id = ?",
                    (status, now, now, error, session_id),
                )
            else:
                await db.execute(
                    "UPDATE sessions SET status = ?, updated_at = ?, error = ? WHERE id = ?",
                    (status, now, error, session_id),
                )
            await db.commit()

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        agent: str | None = None,
        cost: float = 0.0,
    ):
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO session_messages (session_id, role, agent, content, cost, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, role, agent, content, cost, time.time()),
            )
            if cost > 0:
                await db.execute(
                    "UPDATE sessions SET total_cost = total_cost + ?, updated_at = ? WHERE id = ?",
                    (cost, time.time(), session_id),
                )
            await db.commit()

    async def save_state(self, session_id: str, state: dict):
        await self.init()
        state_json = json.dumps(state, default=str)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO session_state (session_id, state_json, updated_at)
                   VALUES (?, ?, ?)""",
                (session_id, state_json, time.time()),
            )
            await db.commit()

    async def get_session(self, session_id: str) -> dict | None:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = list(await db.execute_fetchall(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ))
            if not row:
                return None
            session = dict(row[0])

            messages = await db.execute_fetchall(
                "SELECT * FROM session_messages WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            )
            session["messages"] = [dict(m) for m in messages]

            state_row = list(await db.execute_fetchall(
                "SELECT state_json FROM session_state WHERE session_id = ?",
                (session_id,),
            ))
            if state_row:
                session["state"] = json.loads(state_row[0]["state_json"])

            return session

    async def get_recent_sessions(self, limit: int = 20) -> list[dict]:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT id, directive, source, status, created_at, total_cost FROM sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(r) for r in rows]

    async def get_session_messages(self, session_id: str) -> list[dict]:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM session_messages WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            )
            return [dict(r) for r in rows]

    async def get_total_cost(self) -> float:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            result = list(await db.execute_fetchall(
                "SELECT COALESCE(SUM(total_cost), 0) FROM sessions"
            ))
            return float(result[0][0])


# Singleton
session_store = SessionStore()
