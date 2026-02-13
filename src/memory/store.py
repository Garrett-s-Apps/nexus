"""
NEXUS Memory + World State

Two layers:
1. MEMORY — conversation history, project memory, personal context (v0.3, preserved)
2. WORLD STATE — directives, shared context, task board, agent state, events, services (v1.0, new)

Storage: SQLite at ~/.nexus/memory.db
"""

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime, timedelta

from src.config import MEMORY_DB_PATH

DB_PATH = MEMORY_DB_PATH


class Memory:
    def __init__(self):
        self.db_path = DB_PATH
        self._conn = None
        self._lock = threading.Lock()

    def init(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()

    def _create_tables(self):
        c = self._conn.cursor()

        # --- LEGACY TABLES (v0.3) ---
        c.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, source TEXT DEFAULT 'slack',
            category TEXT DEFAULT '', cost REAL DEFAULT 0)""")

        c.execute("""CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
            period_start TEXT NOT NULL, period_end TEXT NOT NULL,
            summary TEXT NOT NULL, message_count INTEGER DEFAULT 0)""")

        c.execute("""CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, path TEXT,
            status TEXT DEFAULT 'discussing', tech_stack TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, total_cost REAL DEFAULT 0)""")

        c.execute("""CREATE TABLE IF NOT EXISTS project_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
            timestamp TEXT NOT NULL, note_type TEXT DEFAULT 'discussion', content TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id))""")

        c.execute("""CREATE TABLE IF NOT EXISTS context (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)""")

        c.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, project_id TEXT, directive TEXT NOT NULL,
            project_path TEXT, status TEXT DEFAULT 'queued', current_step TEXT DEFAULT '',
            progress TEXT DEFAULT '{}', error TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, completed_at TEXT, cost REAL DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES projects(id))""")

        # --- V1 WORLD STATE TABLES ---
        c.execute("""CREATE TABLE IF NOT EXISTS directives (
            id TEXT PRIMARY KEY, text TEXT NOT NULL, status TEXT DEFAULT 'received',
            intent TEXT DEFAULT '', project_path TEXT DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")

        c.execute("""CREATE TABLE IF NOT EXISTS world_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT, directive_id TEXT,
            author TEXT NOT NULL, type TEXT NOT NULL, content TEXT NOT NULL,
            timestamp TEXT NOT NULL, supersedes INTEGER,
            FOREIGN KEY (directive_id) REFERENCES directives(id))""")

        c.execute("""CREATE TABLE IF NOT EXISTS task_board (
            id TEXT PRIMARY KEY, directive_id TEXT, title TEXT NOT NULL,
            description TEXT DEFAULT '', status TEXT DEFAULT 'available',
            claimed_by TEXT, depends_on TEXT DEFAULT '[]', output TEXT DEFAULT '',
            priority INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY (directive_id) REFERENCES directives(id))""")

        c.execute("""CREATE TABLE IF NOT EXISTS agent_state (
            agent_id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
            model TEXT DEFAULT 'haiku', status TEXT DEFAULT 'idle',
            current_task TEXT, last_action TEXT DEFAULT '', updated_at TEXT NOT NULL)""")

        c.execute("""CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
            source TEXT NOT NULL, event_type TEXT NOT NULL, data TEXT DEFAULT '{}')""")

        c.execute("""CREATE TABLE IF NOT EXISTS running_services (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, pid INTEGER, port INTEGER,
            protocol TEXT DEFAULT 'http', status TEXT DEFAULT 'starting',
            project_path TEXT, started_at TEXT, last_health TEXT, url TEXT, log_path TEXT)""")

        c.execute("""CREATE TABLE IF NOT EXISTS defects (
            id TEXT PRIMARY KEY, directive_id TEXT, task_id TEXT,
            title TEXT NOT NULL, description TEXT NOT NULL,
            severity TEXT DEFAULT 'medium', status TEXT DEFAULT 'open',
            filed_by TEXT NOT NULL, assigned_to TEXT,
            file_path TEXT DEFAULT '', line_number INTEGER DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, resolved_at TEXT,
            FOREIGN KEY (directive_id) REFERENCES directives(id))""")

        c.execute("""CREATE TABLE IF NOT EXISTS peer_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            directive_id TEXT, participants TEXT NOT NULL,
            question TEXT NOT NULL, decision TEXT NOT NULL,
            rationale TEXT DEFAULT '', timestamp TEXT NOT NULL,
            FOREIGN KEY (directive_id) REFERENCES directives(id))""")

        c.execute("CREATE INDEX IF NOT EXISTS idx_events_since ON event_log(id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_world_ctx_directive ON world_context(directive_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_task_board_status ON task_board(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_agent_status ON agent_state(status)")

        self._conn.commit()

    # === MESSAGES ===
    def add_message(self, role, content, source="slack", category="", cost=0.0):
        with self._lock:
            c = self._conn.cursor()
            c.execute("INSERT INTO messages (timestamp,role,content,source,category,cost) VALUES (?,?,?,?,?,?)",
                      (datetime.now(UTC).isoformat(), role, content, source, category, cost))
            self._conn.commit()

    def get_recent_messages(self, limit=50):
        c = self._conn.cursor()
        c.execute("SELECT role,content,timestamp FROM messages ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]; rows.reverse(); return rows

    def get_messages_since(self, hours=24):
        since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        c = self._conn.cursor()
        c.execute("SELECT role,content,timestamp FROM messages WHERE timestamp>? ORDER BY id", (since,))
        return [dict(r) for r in c.fetchall()]

    def get_message_count(self):
        return self._conn.cursor().execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    # === SUMMARIES ===
    def add_summary(self, summary, period_start, period_end, message_count):
        with self._lock:
            c = self._conn.cursor()
            c.execute("INSERT INTO summaries (timestamp,period_start,period_end,summary,message_count) VALUES (?,?,?,?,?)",
                      (datetime.now(UTC).isoformat(), period_start, period_end, summary, message_count))
            self._conn.commit()

    def get_recent_summaries(self, limit=10):
        c = self._conn.cursor()
        c.execute("SELECT summary,period_start,period_end,message_count FROM summaries ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]; rows.reverse(); return rows

    def get_unsummarized_count(self):
        c = self._conn.cursor()
        c.execute("SELECT MAX(period_end) FROM summaries")
        row = c.fetchone(); last = row[0] if row[0] else "1970-01-01"
        return c.execute("SELECT COUNT(*) FROM messages WHERE timestamp>?", (last,)).fetchone()[0]

    # === PROJECTS ===
    def create_project(self, project_id, name, description="", path="", tech_stack=""):
        now = datetime.now(UTC).isoformat()
        with self._lock:
            c = self._conn.cursor()
            c.execute("""INSERT INTO projects (id,name,description,path,tech_stack,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,description=excluded.description,path=excluded.path,
                tech_stack=excluded.tech_stack,updated_at=excluded.updated_at""",
                      (project_id, name, description, path, tech_stack, now, now))
            self._conn.commit()

    def get_project(self, project_id):
        row = self._conn.cursor().execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None

    def get_active_projects(self):
        c = self._conn.cursor()
        c.execute("SELECT * FROM projects WHERE status!='archived' ORDER BY updated_at DESC")
        return [dict(r) for r in c.fetchall()]

    def update_project_status(self, project_id, status, cost=0):
        with self._lock:
            self._conn.cursor().execute(
                "UPDATE projects SET status=?,total_cost=total_cost+?,updated_at=? WHERE id=?",
                (status, cost, datetime.now(UTC).isoformat(), project_id))
            self._conn.commit()

    def add_project_note(self, project_id, content, note_type="discussion"):
        with self._lock:
            self._conn.cursor().execute(
                "INSERT INTO project_notes (project_id,timestamp,note_type,content) VALUES (?,?,?,?)",
                (project_id, datetime.now(UTC).isoformat(), note_type, content))
            self._conn.commit()

    def get_project_notes(self, project_id, limit=20):
        c = self._conn.cursor()
        c.execute("SELECT * FROM project_notes WHERE project_id=? ORDER BY id DESC LIMIT ?", (project_id, limit))
        rows = [dict(r) for r in c.fetchall()]; rows.reverse(); return rows

    def search_projects(self, query):
        c = self._conn.cursor()
        c.execute("SELECT * FROM projects WHERE name LIKE ? OR description LIKE ? ORDER BY updated_at DESC",
                  (f"%{query}%", f"%{query}%"))
        return [dict(r) for r in c.fetchall()]

    # === PERSONAL CONTEXT ===
    def set_context(self, key, value):
        with self._lock:
            self._conn.cursor().execute(
                "INSERT INTO context (key,value,updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (key, value, datetime.now(UTC).isoformat()))
            self._conn.commit()

    def get_context(self, key):
        row = self._conn.cursor().execute("SELECT value FROM context WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def get_all_context(self):
        return {r["key"]: r["value"] for r in self._conn.cursor().execute("SELECT key,value FROM context").fetchall()}

    # === LEGACY TASKS ===
    def create_task(self, task_id, directive, project_path="", project_id=""):
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.cursor().execute(
                "INSERT INTO tasks (id,project_id,directive,project_path,status,created_at,updated_at) VALUES (?,?,?,?,'queued',?,?)",
                (task_id, project_id, directive, project_path, now, now))
            self._conn.commit()
        return {"id": task_id, "status": "queued"}

    def update_task(self, task_id, status=None, current_step=None, progress=None, error=None, cost=None):
        updates, values = ["updated_at=?"], [datetime.now(UTC).isoformat()]
        _TASK_COLS = {"status", "completed_at", "current_step", "progress", "error", "cost"}
        if status: updates.append("status=?"); values.append(status)
        if status == "complete": updates.append("completed_at=?"); values.append(datetime.now(UTC).isoformat())
        if current_step: updates.append("current_step=?"); values.append(current_step)
        if progress: updates.append("progress=?"); values.append(json.dumps(progress))
        if error: updates.append("error=?"); values.append(error)
        if cost is not None: updates.append("cost=?"); values.append(cost)
        # Validate column names are from the known set
        cols_used = {u.split("=")[0] for u in updates}
        if not cols_used <= _TASK_COLS:
            raise ValueError(f"Invalid columns: {cols_used - _TASK_COLS}")
        values.append(task_id)
        with self._lock:
            self._conn.cursor().execute(f"UPDATE tasks SET {','.join(updates)} WHERE id=?", values)  # noqa: S608
            self._conn.commit()

    def get_task(self, task_id):
        row = self._conn.cursor().execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_pending_tasks(self):
        c = self._conn.cursor()
        c.execute("SELECT * FROM tasks WHERE status IN ('queued','running','retrying') ORDER BY created_at")
        return [dict(r) for r in c.fetchall()]

    def get_recent_tasks(self, limit=10):
        c = self._conn.cursor()
        c.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in c.fetchall()]

    # === V1: DIRECTIVES ===
    def create_directive(self, directive_id, text, intent="", project_path=""):
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.cursor().execute(
                "INSERT INTO directives (id,text,status,intent,project_path,created_at,updated_at) VALUES (?,?,'received',?,?,?,?)",
                (directive_id, text, intent, project_path, now, now))
            self._conn.commit()
        self.emit_event("system", "directive_created", {"id": directive_id, "text": text[:200]})
        return {"id": directive_id, "text": text, "status": "received"}

    def get_directive(self, directive_id):
        row = self._conn.cursor().execute("SELECT * FROM directives WHERE id=?", (directive_id,)).fetchone()
        return dict(row) if row else None

    def get_active_directive(self):
        row = self._conn.cursor().execute(
            "SELECT * FROM directives WHERE status NOT IN ('complete','cancelled') ORDER BY created_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def update_directive(self, directive_id, **kwargs):
        _DIRECTIVE_COLS = {"status", "intent", "project_path", "updated_at"}
        updates, values = ["updated_at=?"], [datetime.now(UTC).isoformat()]
        for k, v in kwargs.items():
            if k in ("status", "intent", "project_path"):
                updates.append(f"{k}=?"); values.append(v)
        values.append(directive_id)
        with self._lock:
            self._conn.cursor().execute(f"UPDATE directives SET {','.join(updates)} WHERE id=?", values)  # noqa: S608
            self._conn.commit()

    # === V1: WORLD CONTEXT ===
    def post_context(self, author, ctx_type, content, directive_id="", supersedes=None):
        if not isinstance(content, str): content = json.dumps(content)
        with self._lock:
            c = self._conn.cursor()
            c.execute("INSERT INTO world_context (directive_id,author,type,content,timestamp,supersedes) VALUES (?,?,?,?,?,?)",
                      (directive_id, author, ctx_type, content, datetime.now(UTC).isoformat(), supersedes))
            self._conn.commit()
            entry_id = c.lastrowid
        self.emit_event(author, "context_posted", {"id": entry_id, "type": ctx_type, "preview": content[:200]})
        return entry_id

    def get_context_for_directive(self, directive_id, limit=50):
        c = self._conn.cursor()
        c.execute("SELECT * FROM world_context WHERE directive_id=? ORDER BY id DESC LIMIT ?", (directive_id, limit))
        rows = [dict(r) for r in c.fetchall()]; rows.reverse(); return rows

    def get_latest_context(self, directive_id, ctx_type=None):
        c = self._conn.cursor()
        if ctx_type:
            c.execute("SELECT * FROM world_context WHERE directive_id=? AND type=? ORDER BY id DESC LIMIT 1", (directive_id, ctx_type))
        else:
            c.execute("SELECT * FROM world_context WHERE directive_id=? ORDER BY id DESC LIMIT 1", (directive_id,))
        row = c.fetchone(); return dict(row) if row else None

    def get_context_by_type(self, directive_id, ctx_type):
        c = self._conn.cursor()
        c.execute("SELECT * FROM world_context WHERE directive_id=? AND type=? ORDER BY id", (directive_id, ctx_type))
        return [dict(r) for r in c.fetchall()]

    def has_interruption(self, directive_id, since_id=0):
        c = self._conn.cursor()
        c.execute("SELECT * FROM world_context WHERE directive_id=? AND id>? AND type IN ('interruption','feedback','garrett_message') ORDER BY id LIMIT 1",
                  (directive_id, since_id))
        row = c.fetchone(); return dict(row) if row else None

    # === V1: TASK BOARD ===
    def create_board_task(self, task_id, directive_id, title, description="", depends_on=None, priority=0):
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.cursor().execute(
                "INSERT INTO task_board (id,directive_id,title,description,status,depends_on,priority,created_at,updated_at) VALUES (?,?,?,?,'available',?,?,?,?)",
                (task_id, directive_id, title, description, json.dumps(depends_on or []), priority, now, now))
            self._conn.commit()
        self.emit_event("system", "task_created", {"id": task_id, "title": title})
        return {"id": task_id, "title": title, "status": "available"}

    def claim_task(self, task_id, agent_id):
        with self._lock:
            c = self._conn.cursor()
            c.execute("UPDATE task_board SET status='claimed',claimed_by=?,updated_at=? WHERE id=? AND status='available'",
                      (agent_id, datetime.now(UTC).isoformat(), task_id))
            self._conn.commit()
            ok = c.rowcount > 0
        if ok: self.emit_event(agent_id, "task_claimed", {"task_id": task_id})
        return ok

    def start_board_task(self, task_id):
        with self._lock:
            self._conn.cursor().execute("UPDATE task_board SET status='in_progress',updated_at=? WHERE id=?",
                                         (datetime.now(UTC).isoformat(), task_id))
            self._conn.commit()

    def complete_board_task(self, task_id, output=""):
        with self._lock:
            self._conn.cursor().execute("UPDATE task_board SET status='complete',output=?,updated_at=? WHERE id=?",
                                         (output, datetime.now(UTC).isoformat(), task_id))
            self._conn.commit()
        self.emit_event("system", "task_completed", {"task_id": task_id})

    def fail_board_task(self, task_id, error=""):
        with self._lock:
            self._conn.cursor().execute("UPDATE task_board SET status='failed',output=?,updated_at=? WHERE id=?",
                                         (f"ERROR: {error}", datetime.now(UTC).isoformat(), task_id))
            self._conn.commit()
        self.emit_event("system", "task_failed", {"task_id": task_id, "error": error[:200]})

    def reset_board_task(self, task_id):
        with self._lock:
            self._conn.cursor().execute("UPDATE task_board SET status='available',claimed_by=NULL,output=NULL,updated_at=? WHERE id=?",
                                         (datetime.now(UTC).isoformat(), task_id))
            self._conn.commit()

    def get_available_tasks(self, directive_id=None):
        c = self._conn.cursor()
        if directive_id:
            c.execute("SELECT * FROM task_board WHERE status='available' AND directive_id=? ORDER BY priority DESC,created_at", (directive_id,))
        else:
            c.execute("SELECT * FROM task_board WHERE status='available' ORDER BY priority DESC,created_at")
        return [dict(r) for r in c.fetchall()]

    def get_board_tasks(self, directive_id):
        c = self._conn.cursor()
        c.execute("SELECT * FROM task_board WHERE directive_id=? ORDER BY priority DESC,created_at", (directive_id,))
        return [dict(r) for r in c.fetchall()]

    def are_dependencies_met(self, task_id):
        row = self._conn.cursor().execute("SELECT depends_on FROM task_board WHERE id=?", (task_id,)).fetchone()
        if not row: return False
        deps = json.loads(row[0])
        if not deps: return True
        ph = ",".join("?" for _ in deps)
        return self._conn.cursor().execute(f"SELECT COUNT(*) FROM task_board WHERE id IN ({ph}) AND status='complete'", deps).fetchone()[0] == len(deps)  # noqa: S608

    # === V1: AGENT STATE ===
    def register_agent(self, agent_id, name, role, model="haiku"):
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.cursor().execute(
                "INSERT INTO agent_state (agent_id,name,role,model,status,updated_at) VALUES (?,?,?,?,'idle',?) "
                "ON CONFLICT(agent_id) DO UPDATE SET name=excluded.name,role=excluded.role,model=excluded.model,updated_at=excluded.updated_at",
                (agent_id, name, role, model, now))
            self._conn.commit()

    def update_agent(self, agent_id, status=None, current_task=None, last_action=None):
        _AGENT_COLS = {"status", "current_task", "last_action", "updated_at"}
        updates, values = ["updated_at=?"], [datetime.now(UTC).isoformat()]
        if status: updates.append("status=?"); values.append(status)
        if current_task is not None: updates.append("current_task=?"); values.append(current_task)
        if last_action: updates.append("last_action=?"); values.append(last_action)
        values.append(agent_id)
        with self._lock:
            self._conn.cursor().execute(f"UPDATE agent_state SET {','.join(updates)} WHERE agent_id=?", values)  # noqa: S608
            self._conn.commit()

    def get_agent(self, agent_id):
        row = self._conn.cursor().execute("SELECT * FROM agent_state WHERE agent_id=?", (agent_id,)).fetchone()
        return dict(row) if row else None

    def get_idle_agents(self):
        return [dict(r) for r in self._conn.cursor().execute("SELECT * FROM agent_state WHERE status='idle'").fetchall()]

    def get_all_agents(self):
        return [dict(r) for r in self._conn.cursor().execute("SELECT * FROM agent_state ORDER BY agent_id").fetchall()]

    def get_working_agents(self):
        return [dict(r) for r in self._conn.cursor().execute("SELECT * FROM agent_state WHERE status IN ('working','thinking')").fetchall()]

    # === V1: EVENT LOG ===
    def emit_event(self, source, event_type, data=None):
        if data and not isinstance(data, str): data = json.dumps(data)
        with self._lock:
            self._conn.cursor().execute("INSERT INTO event_log (timestamp,source,event_type,data) VALUES (?,?,?,?)",
                                         (datetime.now(UTC).isoformat(), source, event_type, data or "{}"))
            self._conn.commit()

    def get_events_since(self, last_id=0, limit=100):
        c = self._conn.cursor()
        c.execute("SELECT * FROM event_log WHERE id>? ORDER BY id LIMIT ?", (last_id, limit))
        return [dict(r) for r in c.fetchall()]

    def get_latest_event_id(self):
        c = self._conn.cursor()
        c.execute("SELECT MAX(id) FROM event_log")
        row = c.fetchone()
        return row[0] or 0

    def get_recent_events(self, limit=50):
        c = self._conn.cursor()
        c.execute("SELECT * FROM event_log ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]; rows.reverse(); return rows

    # === V1: RUNNING SERVICES ===
    def register_service(self, service_id, name, pid=None, port=None, project_path="", url="", log_path=""):
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.cursor().execute(
                "INSERT INTO running_services (id,name,pid,port,status,project_path,started_at,url,log_path) "
                "VALUES (?,?,?,?,'starting',?,?,?,?) ON CONFLICT(id) DO UPDATE SET pid=excluded.pid,port=excluded.port,"
                "status='starting',started_at=excluded.started_at,url=excluded.url",
                (service_id, name, pid, port, project_path, now, url, log_path))
            self._conn.commit()
        self.emit_event("system", "service_registered", {"name": name, "port": port})

    def update_service(self, service_id, **kwargs):
        allowed = {"status", "pid", "port", "url", "last_health", "log_path"}
        updates, values = [], []
        for k, v in kwargs.items():
            if k in allowed: updates.append(f"{k}=?"); values.append(v)
        if not updates: return
        values.append(service_id)
        with self._lock:
            self._conn.cursor().execute(f"UPDATE running_services SET {','.join(updates)} WHERE id=?", values)  # noqa: S608
            self._conn.commit()

    def get_service(self, service_id):
        row = self._conn.cursor().execute("SELECT * FROM running_services WHERE id=?", (service_id,)).fetchone()
        return dict(row) if row else None

    def get_all_services(self):
        return [dict(r) for r in self._conn.cursor().execute("SELECT * FROM running_services ORDER BY name").fetchall()]

    def get_running_services(self):
        return [dict(r) for r in self._conn.cursor().execute("SELECT * FROM running_services WHERE status IN ('running','starting')").fetchall()]

    def remove_service(self, service_id):
        with self._lock:
            self._conn.cursor().execute("DELETE FROM running_services WHERE id=?", (service_id,))
            self._conn.commit()

    # === CONTEXT BUILDING ===
    def build_context_window(self, max_tokens=4000):
        parts = []
        ctx = self.get_all_context()
        if ctx:
            parts.append("ABOUT GARRETT:")
            for k, v in ctx.items(): parts.append(f"  {k}: {v}")

        directive = self.get_active_directive()
        if directive:
            parts.append(f"\nCURRENT DIRECTIVE: {directive['text']}")
            parts.append(f"STATUS: {directive['status']}")
            board = self.get_board_tasks(directive["id"])
            if board:
                parts.append("\nTASK BOARD:")
                for t in board:
                    claimed = f" -> {t['claimed_by']}" if t['claimed_by'] else ""
                    parts.append(f"  [{t['status']}] {t['title']}{claimed}")

        projects = self.get_active_projects()
        if projects:
            parts.append("\nACTIVE PROJECTS:")
            for p in projects[:10]:
                parts.append(f"  - {p['name']} ({p['status']}): {(p['description'] or '')[:100]}")

        services = self.get_running_services()
        if services:
            parts.append("\nRUNNING SERVICES:")
            for s in services:
                parts.append(f"  - {s['name']}: {s['url']} (PID {s['pid']}, {s['status']})")

        agents = self.get_working_agents()
        if agents:
            parts.append("\nAGENTS WORKING:")
            for a in agents: parts.append(f"  - {a['name']}: {a['last_action'][:80]}")

        summaries = self.get_recent_summaries(3)
        if summaries:
            parts.append("\nRECENT HISTORY:")
            for s in summaries: parts.append(f"  {s['summary'][:200]}")

        context = "\n".join(parts)
        if len(context) > max_tokens * 4: context = context[:max_tokens * 4]
        return context

    def build_message_history(self, max_messages=30):
        msgs = self.get_recent_messages(max_messages)
        return [{"role": m["role"], "content": m["content"]} for m in msgs]

    def get_world_snapshot(self):
        directive = self.get_active_directive()
        return {
            "directive": directive,
            "agents": self.get_all_agents(),
            "task_board": self.get_board_tasks(directive["id"]) if directive else [],
            "services": self.get_all_services(),
            "defects": self.get_open_defects(directive["id"]) if directive else [],
            "recent_events": self.get_recent_events(30),
            "projects": self.get_active_projects(),
            "stats": {
                "total_messages": self.get_message_count(),
                "active_agents": len(self.get_working_agents()),
                "pending_tasks": len(self.get_available_tasks()),
            },
        }

    # === DEFECTS ===
    def create_defect(self, defect_id, directive_id, task_id, title, description,
                      severity="medium", filed_by="", file_path="", line_number=0):
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.cursor().execute(
                "INSERT INTO defects (id,directive_id,task_id,title,description,severity,status,filed_by,file_path,line_number,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,'open',?,?,?,?,?)",
                (defect_id, directive_id, task_id, title, description, severity, filed_by, file_path, line_number, now, now))
            self._conn.commit()
        self.emit_event(filed_by, "defect_filed", {"id": defect_id, "title": title, "severity": severity})

    def get_open_defects(self, directive_id=None):
        c = self._conn.cursor()
        if directive_id:
            c.execute("SELECT * FROM defects WHERE directive_id=? AND status='open' ORDER BY created_at", (directive_id,))
        else:
            c.execute("SELECT * FROM defects WHERE status='open' ORDER BY created_at")
        return [dict(r) for r in c.fetchall()]

    def get_defects_for_task(self, task_id):
        c = self._conn.cursor()
        c.execute("SELECT * FROM defects WHERE task_id=? ORDER BY created_at", (task_id,))
        return [dict(r) for r in c.fetchall()]

    def resolve_defect(self, defect_id, resolved_by=""):
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.cursor().execute(
                "UPDATE defects SET status='resolved',resolved_at=?,updated_at=? WHERE id=?", (now, now, defect_id))
            self._conn.commit()
        self.emit_event(resolved_by, "defect_resolved", {"id": defect_id})

    def assign_defect(self, defect_id, assigned_to):
        with self._lock:
            self._conn.cursor().execute(
                "UPDATE defects SET assigned_to=?,updated_at=? WHERE id=?",
                (assigned_to, datetime.now(UTC).isoformat(), defect_id))
            self._conn.commit()

    # === PEER DECISIONS ===
    def record_peer_decision(self, directive_id, participants, question, decision, rationale=""):
        with self._lock:
            self._conn.cursor().execute(
                "INSERT INTO peer_decisions (directive_id,participants,question,decision,rationale,timestamp) VALUES (?,?,?,?,?,?)",
                (directive_id, json.dumps(participants) if isinstance(participants, list) else participants,
                 question, decision, rationale, datetime.now(UTC).isoformat()))
            self._conn.commit()
        self.emit_event("peer", "decision_made", {"participants": participants, "decision": decision[:200]})


memory = Memory()
